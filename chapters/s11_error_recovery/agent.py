from typing import Any

from context_compact import (
    L3_L1_L2_compact,
    compact_history,
    estimate_size,
    reactive_compact,
)
from error_recovery import (
    RecoveryState,
    call_with_retries,
    completion_hit_token_limit,
    is_context_limit_error,
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


CONTEXT_LIMIT = 640000

rounds_since_todo = 0


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
    recovery = RecoveryState(config.model)
    context = update_context({}, messages)

    for _ in range(max_turns):
        _maybe_add_todo_reminder(messages)
        memories_content = load_memories(messages)
        pre_compress = _serializable_messages(messages)

        L3_L1_L2_compact(messages, allow_lossy=True)

        if estimate_size(messages) > CONTEXT_LIMIT:
            print("[auto compact]")
            messages[:] = with_system_message(compact_history(messages))

        needs_continuation = False
        try:
            context = update_context(context, messages)
            messages[:] = with_system_message(messages, context)
            request_messages = with_relevant_memories(
                openai_compatible_messages(messages),
                memories_content,
            )

            def request(model: str, max_tokens: int) -> Any:
                return client.chat.completions.create(
                    model=model,
                    messages=request_messages,
                    tools=TOOLS,
                    max_tokens=max_tokens,
                )

            response = call_with_retries(request, recovery)
            while completion_hit_token_limit(response):
                message = response.choices[0].message
                escalation = recovery.escalate_tokens_once()
                if escalation is not None:
                    previous, current = escalation
                    print(f"[max_tokens] escalating {previous} -> {current}")
                    response = call_with_retries(request, recovery)
                    continue

                messages.append(message_to_dict(message))
                continuation = recovery.next_continuation()
                if continuation is None:
                    print("[max_tokens] recovery limit reached")
                    return messages
                prompt, count, limit = continuation
                messages.append({"role": "user", "content": prompt})
                print(f"[max_tokens] continuation {count}/{limit}")
                needs_continuation = True
                break
        except Exception as exc:
            if is_context_limit_error(exc) and not recovery.has_reactive_compacted:
                print("[reactive compact]")
                messages[:] = with_system_message(reactive_compact(messages))
                recovery.mark_reactive_compacted()
                continue

            name = type(exc).__name__
            print(f"[unrecoverable] {name}: {str(exc)[:100]}")
            messages.append(
                {"role": "assistant", "content": f"[Error] {name}: {str(exc)[:200]}"}
            )
            return messages

        if needs_continuation:
            continue

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
