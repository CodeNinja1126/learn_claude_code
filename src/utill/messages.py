from typing import Any


Message = dict[str, Any]


def user_message(content: str) -> Message:
    return {"role": "user", "content": content}


def assistant_message(content: str) -> Message:
    return {"role": "assistant", "content": content}


def system_message(content: str) -> Message:
    return {"role": "system", "content": content}
