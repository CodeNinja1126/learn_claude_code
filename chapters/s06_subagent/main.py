from typing import Any
import json

from utill import WORKDIR
from utill.client import create_client, end_client
from utill.config import load_config

from hook import register_hook, trigger_hooks
from hook import (
    context_inject_hook,
    permission_hook,
    log_hook,
    large_output_hook,
    summary_hook,
)
from tool import TOOLS, TOOL_HANDLERS


SYSTEM = f"너는 디렉토리 {WORKDIR}의 코딩 에이전트야. 도구를 활용해 문제를 해결해, 문제를 해결할 때까지 작업을 멈추지 말고 계속해."

ROUNDS_SINCE_TODO = 0


def _message_to_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    return dict(message)


def _parse_tool_args(raw_args: str | None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError as exc:
        return None, f"Error: invalid tool arguments JSON: {exc.msg}"
    if not isinstance(args, dict):
        return None, "Error: tool arguments must be a JSON object"
    return args, None


def _append_tool_result(messages: list[dict[str, Any]], tool_call_id: str, content: str) -> None:
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
    )


def agent_loop(
    messages: list[dict[str, Any]],
    max_turns: int = 8,
) -> list[dict[str, Any]]:
    global ROUNDS_SINCE_TODO

    config = load_config()
    client = create_client(config)

    for _ in range(max_turns):
        if ROUNDS_SINCE_TODO >= 3 and messages:
            messages.append(
                {
                    "role": "user",
                    "content": "<reminder>Update your todos.</reminder>",
                }
            )

        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            tools=TOOLS,
        )

        message = response.choices[0].message
        messages.append(_message_to_dict(message))
        if message.content:
            print(message.content)

        if not message.tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            return messages

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args, parse_error = _parse_tool_args(tool_call.function.arguments)
            if parse_error:
                _append_tool_result(messages, tool_call.id, parse_error)
                continue

            blocked = trigger_hooks("PreToolUse", tool_name, tool_args)
            if blocked:
                _append_tool_result(messages, tool_call.id, blocked)
                print("permission_denied")
                continue

            handler = TOOL_HANDLERS.get(tool_name)
            if handler is None:
                _append_tool_result(messages, tool_call.id, f"Error: unknown tool {tool_name}")
                continue

            try:
                result = handler(**tool_args)
            except Exception as exc:
                result = f"Error: {exc}"

            trigger_hooks("PostToolUse", tool_name, result)

            if tool_name == "todo_write":
                ROUNDS_SINCE_TODO = 0

            _append_tool_result(messages, tool_call.id, result)

        if not any(tc.function.name == "todo_write" for tc in message.tool_calls):
            ROUNDS_SINCE_TODO += 1

    return messages


def main() -> None:
    messages = [{"role": "system", "content": SYSTEM}]

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
