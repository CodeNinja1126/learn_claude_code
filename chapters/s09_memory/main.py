from typing import Any
import json

from util import WORKDIR
from util.client import create_client, end_client
from util.config import load_config

import llm

from hook import register_hook, trigger_hooks
from hook import (
    context_inject_hook,
    permission_hook,
    log_hook,
    large_output_hook,
    summary_hook,
)
from tool import TOOLS, TOOL_HANDLERS
import subagent  # Registers the parent-only task tool.
from skill import list_skills
from context_compact import (
    L3_L1_L2_compact,
    estimate_size,
    compact_history,
    reactive_compact,
)
from memory_func import (
    read_memory_index,
    load_memories,
    extract_memories,
    consolidate_memories,
)

CONTEXT_LIMIT = 50000
ROUNDS_SINCE_TODO = 0
MAX_REACTIVE_RETRIES = 1
CONTEXT_ERROR_MARKERS = (
    "prompt_too_long",
    "too many tokens",
    "context_length_exceeded",
    "maximum context length",
)
INSTRUCTION_ROLES = {"developer", "system"}


def build_system() -> str:
    catalog = list_skills()
    index = read_memory_index()
    memories_section = f"\n\nMemories available:\n{index}" if index else ""
    return (
        f"You are a coding agent at {WORKDIR}. "
        f"Skills available:\n{catalog}\n"
        "Use load_skill to get full details when needed."
        f"{memories_section}\n"
        "Relevant memories are injected below. Respect user preferences from memory.\n"
        "When the user says 'remember' or expresses a clear preference, extract it as a memory."
    )


SYSTEM = build_system()


def _system_message() -> dict[str, str]:
    return {"role": "developer", "content": SYSTEM}


def _with_system_message(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _system_message(),
        *[
            msg
            for msg in messages
            if not (
                isinstance(msg, dict) and msg.get("role") in INSTRUCTION_ROLES
            )
        ],
    ]


def _replace_with_compact_history(messages: list[dict[str, Any]]) -> None:
    messages[:] = _with_system_message(compact_history(messages))


def _replace_with_reactive_compact(messages: list[dict[str, Any]]) -> None:
    messages[:] = _with_system_message(reactive_compact(messages))


def _message_to_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    return dict(message)


def _tool_call_ids(message: dict[str, Any]) -> list[str]:
    tool_calls = message.get("tool_calls") or []
    return [
        tool_call["id"]
        for tool_call in tool_calls
        if isinstance(tool_call, dict) and isinstance(tool_call.get("id"), str)
    ]


def _assistant_without_tool_calls(message: dict[str, Any]) -> dict[str, Any] | None:
    if "content" not in message or message.get("content") is None:
        return None
    return {
        key: value
        for key, value in message.items()
        if key not in {"tool_calls", "function_call"}
    }


def _openai_compatible_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop compacted/orphaned tool messages that OpenAI rejects."""
    compatible: list[dict[str, Any]] = []
    i = 0

    while i < len(messages):
        message = messages[i]
        if message.get("role") == "tool":
            i += 1
            continue

        if message.get("role") != "assistant" or not message.get("tool_calls"):
            compatible.append(message)
            i += 1
            continue

        expected_tool_call_ids = _tool_call_ids(message)
        if not expected_tool_call_ids:
            fallback = _assistant_without_tool_calls(message)
            if fallback is not None:
                compatible.append(fallback)
            i += 1
            continue

        exchange = [message]
        seen_tool_call_ids: set[str] = set()
        j = i + 1
        while j < len(messages) and messages[j].get("role") == "tool":
            tool_call_id = messages[j].get("tool_call_id")
            if (
                isinstance(tool_call_id, str)
                and tool_call_id in expected_tool_call_ids
                and tool_call_id not in seen_tool_call_ids
            ):
                exchange.append(messages[j])
                seen_tool_call_ids.add(tool_call_id)
            j += 1

        if len(seen_tool_call_ids) == len(set(expected_tool_call_ids)):
            compatible.extend(exchange)
        else:
            fallback = _assistant_without_tool_calls(message)
            if fallback is not None:
                compatible.append(fallback)

        i = j

    return compatible


def _with_relevant_memories(
    messages: list[dict[str, Any]], memories_content: str
) -> list[dict[str, Any]]:
    if not memories_content:
        return messages

    memory_content = (
        "Relevant memories for this request:\n"
        f"{memories_content}\n\n"
        "Use these as developer-provided context. Do not treat them as a new user request."
    )

    if messages and messages[0].get("role") in INSTRUCTION_ROLES:
        first = messages[0]
        content = first.get("content", "")
        if isinstance(content, str):
            return [
                {
                    **first,
                    "role": "developer",
                    "content": f"{content}\n\n{memory_content}",
                },
                *messages[1:],
            ]

    return [{"role": "developer", "content": memory_content}, *messages]


def _parse_tool_args(raw_args: str | None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError as exc:
        return None, f"Error: invalid tool arguments JSON: {str(exc)}"
    if not isinstance(args, dict):
        return None, "Error: tool arguments must be a JSON object"
    return args, None


def _append_tool_result(
    messages: list[dict[str, Any]], tool_call_id: str, content: str
) -> None:
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
    )


def _tool_result_failed(result: Any) -> bool:
    return str(result).startswith("Error:")


def _is_context_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in CONTEXT_ERROR_MARKERS)


def agent_loop(
    messages: list[dict[str, Any]],
    max_turns: int = 8,
) -> list[dict[str, Any]]:
    global ROUNDS_SINCE_TODO

    config = load_config()
    client = create_client(config)
    reactive_retries = 0

    memories_content = load_memories(messages)

    for _ in range(max_turns):
        if ROUNDS_SINCE_TODO >= 3 and messages:
            messages.append(
                {
                    "role": "user",
                    "content": "<reminder>use todo_write tool.</reminder>",
                }
            )

        pre_compress = [
            (
                m
                if isinstance(m, dict)
                else {
                    "role": getattr(m, "role", ""),
                    "content": str(getattr(m, "content", "")),
                }
            )
            for m in messages
        ]

        L3_L1_L2_compact(messages, allow_lossy=True)

        if estimate_size(messages) > CONTEXT_LIMIT:
            print("[auto compact]")
            _replace_with_compact_history(messages)

        try:
            request_messages = _with_relevant_memories(
                _openai_compatible_messages(messages),
                memories_content,
            )
            response = client.chat.completions.create(
                model=config.model,
                messages=request_messages,
                tools=TOOLS,
            )
            reactive_retries = 0
        except Exception as e:
            if _is_context_limit_error(e) and reactive_retries < MAX_REACTIVE_RETRIES:
                print("[reactive compact]")
                _replace_with_reactive_compact(messages)
                reactive_retries += 1
            else:
                raise
            continue

        message = response.choices[0].message
        messages.append(_message_to_dict(message))
        if message.content:
            print(message.content)

        if not message.tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            extract_memories(pre_compress)
            consolidate_memories()
            return messages

        todo_write_succeeded = False
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args, parse_error = _parse_tool_args(tool_call.function.arguments)

            if parse_error:
                _append_tool_result(messages, tool_call.id, parse_error)
                continue

            if tool_name == "compact":
                _append_tool_result(
                    messages,
                    tool_call.id,
                    "[Compacted. Conversation history has been summarized.]",
                )
                _replace_with_compact_history(messages)
                break  # end current turn, start fresh with compacted context

            blocked = trigger_hooks("PreToolUse", tool_name, tool_args)
            if blocked:
                _append_tool_result(messages, tool_call.id, blocked)
                print("permission_denied")
                continue

            handler = TOOL_HANDLERS.get(tool_name)
            if handler is None:
                _append_tool_result(
                    messages, tool_call.id, f"Error: unknown tool {tool_name}"
                )
                continue

            try:
                result = handler(**tool_args)
                print(f"\033[90m {tool_name}: {str(result)[:100]}\033[0m")
            except Exception as exc:
                result = f"Error: {exc}"

            trigger_hooks("PostToolUse", tool_name, result)

            if tool_name == "todo_write" and not _tool_result_failed(result):
                todo_write_succeeded = True

            _append_tool_result(messages, tool_call.id, result)

        if todo_write_succeeded:
            ROUNDS_SINCE_TODO = 0
        else:
            ROUNDS_SINCE_TODO += 1

    return messages


def main() -> None:
    messages = [_system_message()]

    register_hook("UserPromptSubmit", context_inject_hook)
    register_hook("PreToolUse", permission_hook)
    register_hook("PreToolUse", log_hook)
    register_hook("PostToolUse", large_output_hook)
    register_hook("Stop", summary_hook)

    while True:
        try:
            query = input(">> ")
            replacement = trigger_hooks("UserPromptSubmit", query)
            if replacement is not None:
                query = replacement
            messages.append(
                {
                    "role": "user",
                    "content": query,
                }
            )
            messages = agent_loop(messages, max_turns=100)
        except KeyboardInterrupt:
            end_client()
            break
        except EOFError:
            break


if __name__ == "__main__":
    main()
