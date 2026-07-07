import json
from typing import Any

from hook import trigger_hooks
from tool import TOOL_HANDLERS, TOOLS
from util import WORKDIR
from util.client import create_client
from util.config import load_config

SUB_SYSTEM = (
    f"너는 디렉토리 {WORKDIR}에서 실행되는 하위 코딩 에이전트야. "
    "주어진 하위 작업만 해결하고, 완료되면 부모 에이전트에게 전달할 간결한 요약을 반환해. "
    "다른 하위 에이전트를 다시 만들지는 마."
)

# Keep the child context bounded: it can use ordinary tools, but cannot spawn more
# tasks recursively.
SUB_TOOLS = [
    tool
    for tool in TOOLS
    if tool.get("function", {}).get("name") != "task" and \
        tool.get("function", {}).get("name") != "todo_write" and \
        tool.get("function", {}).get("name") != "load_skill"
]
SUB_HANDLERS = {
    name: handler
    for name, handler in TOOL_HANDLERS.items()
    if name != "task" and name != "todo_write" and name != "load_skill"
}

_SUB_CONFIG: Any | None = None
_SUB_CLIENT: Any | None = None


def _get_subagent_runtime() -> tuple[Any, Any]:
    global _SUB_CONFIG, _SUB_CLIENT
    if _SUB_CONFIG is None:
        _SUB_CONFIG = load_config()
    if _SUB_CLIENT is None:
        _SUB_CLIENT = create_client(_SUB_CONFIG)
    return _SUB_CONFIG, _SUB_CLIENT


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


def spawn_subagent(description: str) -> str:
    print("\n\033[35m[Subagent spawned]\033[0m")
    messages = [
        {"role": "system", "content": SUB_SYSTEM},
        {"role": "user", "content": description},
    ]

    config, client = _get_subagent_runtime()

    for _ in range(30):
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            tools=SUB_TOOLS,
        )
        message = response.choices[0].message
        messages.append(_message_to_dict(message))

        if not message.tool_calls:
            print("\033[35m[Subagent done]\033[0m")
            return message.content or "(no summary)"

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args, parse_error = _parse_tool_args(tool_call.function.arguments)
            if parse_error:
                _append_tool_result(messages, tool_call.id, parse_error)
                continue

            blocked = trigger_hooks("PreToolUse", tool_name, tool_args)
            if blocked:
                _append_tool_result(messages, tool_call.id, blocked)
                print("  \033[90m[sub] permission_denied\033[0m")
                continue

            handler = SUB_HANDLERS.get(tool_name)
            if handler is None:
                output = f"Error: unknown tool {tool_name}"
            else:
                try:
                    output = handler(**tool_args)
                except Exception as exc:
                    output = f"Error: {exc}"

            trigger_hooks("PostToolUse", tool_name, output)
            print(f"  \033[90m[sub] {tool_name}: {str(output)[:100]}\033[0m")
            _append_tool_result(messages, tool_call.id, output)

    print("\033[35m[Subagent done]\033[0m")
    return "Subagent stopped after 30 turns without final answer."


def register_task_tool() -> None:
    if "task" in TOOL_HANDLERS:
        return
    TOOLS.append(
        {
            "type": "function",
            "function": {
                "name": "task",
                "description": (
                    "Launch a subagent to handle a bounded subtask. "
                    "Returns only the final conclusion."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"description": {"type": "string"}},
                    "required": ["description"],
                },
            },
        }
    )
    TOOL_HANDLERS["task"] = spawn_subagent


register_task_tool()
