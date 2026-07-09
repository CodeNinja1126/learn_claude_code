from typing import Any

from context_compact import (
    L3_L1_L2_compact,
    compact_history,
    estimate_size,
    reactive_compact,
)
from hook import trigger_hooks
from memory import consolidate_memories, extract_memories, load_memories
from messages import (
    append_tool_result,
    message_to_dict,
    openai_compatible_messages,
    parse_tool_args,
    tool_result_failed,
    with_relevant_memories,
)
from system_prompt import update_context, with_system_message
from tool import TOOL_HANDLERS, TOOLS
from util.client import create_client
from util.config import load_config


CONTEXT_LIMIT = 50000
MAX_REACTIVE_RETRIES = 1
CONTEXT_ERROR_MARKERS = (
    "prompt_too_long",
    "too many tokens",
    "context_length_exceeded",
    "maximum context length",
)

rounds_since_todo = 0


def _is_context_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in CONTEXT_ERROR_MARKERS)


def _serializable_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        (
            message
            if isinstance(message, dict)
            else {
                "role": getattr(message, "role", ""),
                "content": str(getattr(message, "content", "")),
            }
        )
        for message in messages
    ]


def _maybe_add_todo_reminder(messages: list[dict[str, Any]]) -> None:
    if rounds_since_todo < 3 or not messages:
        return
    messages.append(
        {
            "role": "user",
            "content": "<reminder>use todo_write tool.</reminder>",
        }
    )


def _execute_tool_call(
    messages: list[dict[str, Any]],
    tool_call: Any,
) -> bool | None:
    tool_name = tool_call.function.name
    tool_args, parse_error = parse_tool_args(tool_call.function.arguments)

    if parse_error:
        append_tool_result(messages, tool_call.id, parse_error)
        return False

    if tool_name == "compact":
        append_tool_result(
            messages,
            tool_call.id,
            "[Compacted. Conversation history has been summarized.]",
        )
        messages[:] = with_system_message(compact_history(messages))
        return None

    blocked = trigger_hooks("PreToolUse", tool_name, tool_args)
    if blocked:
        append_tool_result(messages, tool_call.id, blocked)
        print("permission_denied")
        return False

    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        append_tool_result(messages, tool_call.id, f"Error: unknown tool {tool_name}")
        return False

    try:
        result = handler(**tool_args)
        print(f"\033[90m {tool_name}: {str(result)[:100]}\033[0m")
    except Exception as exc:
        result = f"Error: {exc}"

    trigger_hooks("PostToolUse", tool_name, result)
    append_tool_result(messages, tool_call.id, result)
    return tool_name == "todo_write" and not tool_result_failed(result)


def agent_loop(
    messages: list[dict[str, Any]],
    max_turns: int = 8,
) -> list[dict[str, Any]]:
    global rounds_since_todo

    config = load_config()
    client = create_client(config)
    reactive_retries = 0
    context = update_context({}, messages)

    for _ in range(max_turns):
        _maybe_add_todo_reminder(messages)
        memories_content = load_memories(messages)
        pre_compress = _serializable_messages(messages)

        L3_L1_L2_compact(messages, allow_lossy=True)

        if estimate_size(messages) > CONTEXT_LIMIT:
            print("[auto compact]")
            messages[:] = with_system_message(compact_history(messages))

        try:
            context = update_context(context, messages)
            messages[:] = with_system_message(messages, context)
            request_messages = with_relevant_memories(
                openai_compatible_messages(messages),
                memories_content,
            )
            response = client.chat.completions.create(
                model=config.model,
                messages=request_messages,
                tools=TOOLS,
            )
            reactive_retries = 0
        except Exception as exc:
            if _is_context_limit_error(exc) and reactive_retries < MAX_REACTIVE_RETRIES:
                print("[reactive compact]")
                messages[:] = with_system_message(reactive_compact(messages))
                reactive_retries += 1
                continue
            raise

        message = response.choices[0].message
        messages.append(message_to_dict(message))
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
            result = _execute_tool_call(messages, tool_call)
            if result is None:
                break
            todo_write_succeeded = todo_write_succeeded or result

        if todo_write_succeeded:
            rounds_since_todo = 0
        else:
            rounds_since_todo += 1

    return messages
