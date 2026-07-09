from typing import Any
import json


INSTRUCTION_ROLES = {"developer", "system"}


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        elif getattr(block, "type", None) == "text":
            parts.append(str(getattr(block, "text", "")))
    return " ".join(part for part in parts if part)


def message_to_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    return dict(message)


def parse_tool_args(raw_args: str | None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError as exc:
        return None, f"Error: invalid tool arguments JSON: {exc.msg}"
    if not isinstance(args, dict):
        return None, "Error: tool arguments must be a JSON object"
    return args, None


def append_tool_result(
    messages: list[dict[str, Any]], tool_call_id: str, content: str
) -> None:
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
    )


def tool_result_failed(result: Any) -> bool:
    return str(result).startswith("Error:")


def _tool_call_ids(message: dict[str, Any]) -> list[str]:
    tool_calls = message.get("tool_calls") or []
    return [
        tool_call["id"]
        for tool_call in tool_calls
        if isinstance(tool_call, dict) and isinstance(tool_call.get("id"), str)
    ]


def _assistant_content_message(message: dict[str, Any]) -> dict[str, Any] | None:
    if "content" not in message or message.get("content") is None:
        return None
    return {
        key: value
        for key, value in message.items()
        if key not in {"tool_calls", "function_call"}
    }


def openai_compatible_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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
            content_message = _assistant_content_message(message)
            if content_message is not None:
                compatible.append(content_message)
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
            content_message = _assistant_content_message(message)
            if content_message is not None:
                compatible.append(content_message)

        i = j

    return compatible


def with_relevant_memories(
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
