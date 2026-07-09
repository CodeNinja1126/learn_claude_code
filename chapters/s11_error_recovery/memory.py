from typing import Any
import json
import re
import time

from memory_store import (
    MEMORY_DIR,
    list_memory_files,
    read_memory_file,
    write_memory_file,
)
from messages import content_to_text
from util.client import create_client
from util.config import load_config


CONSOLIDATE_THRESHOLD = 10
MEMORY_TYPES = ["user", "feedback", "project", "reference"]


def _completion_text(prompt: str, max_tokens: int) -> str:
    config = load_config()
    client = create_client(config)
    response = client.chat.completions.create(
        model=config.model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def _json_array_from_text(text: str, *, greedy: bool = False) -> list[Any]:
    pattern = r"\[.*\]" if greedy else r"\[.*?\]"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return []
    value = json.loads(match.group())
    return value if isinstance(value, list) else []


def _warn_memory_failure(action: str, exc: Exception) -> None:
    print(f"\033[90m[Memory: {action} failed: {exc}]\033[0m")


def _recent_user_text(messages: list[dict[str, Any]], max_items: int = 3) -> str:
    recent_texts: list[str] = []
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = content_to_text(msg.get("content", ""))
        if content:
            recent_texts.append(content)
        if len(recent_texts) >= max_items:
            break
    return " ".join(reversed(recent_texts))[:2000]


def _keyword_memory_matches(
    files: list[dict[str, Any]], recent: str, max_items: int
) -> list[str]:
    keywords = [word.lower() for word in recent.split() if len(word) > 3]
    selected: list[str] = []
    for item in files:
        text = (item["name"] + " " + item["description"]).lower()
        if any(keyword in text for keyword in keywords):
            selected.append(item["filename"])
            if len(selected) >= max_items:
                break
    return selected


def _memory_fields(mem: Any) -> tuple[str, str, str, str] | None:
    if not isinstance(mem, dict):
        return None
    name = mem.get("name", f"memory_{int(time.time())}")
    mem_type = mem.get("type", "user")
    description = mem.get("description", "")
    body = mem.get("body", "")
    if mem_type not in MEMORY_TYPES:
        mem_type = "user"
    if not description or not body:
        return None
    return name, mem_type, description, body


def select_relevant_memories(
    messages: list[dict[str, Any]], max_items: int = 5
) -> list[str]:
    files = list_memory_files()
    if not files:
        return []

    recent = _recent_user_text(messages)
    if not recent.strip():
        return []

    catalog = "\n".join(
        f"{index}: {item['name']} — {item['description']}"
        for index, item in enumerate(files)
    )
    prompt = (
        "Given the recent conversation and the memory catalog below, "
        "select the indices of memories that are clearly relevant. "
        "Return ONLY a JSON array of integers, e.g. [0, 3]. "
        "If none are relevant, return [].\n\n"
        f"Recent conversation:\n{recent}\n\n"
        f"Memory catalog:\n{catalog}"
    )

    try:
        indices = _json_array_from_text(_completion_text(prompt, max_tokens=200))
    except Exception as exc:
        _warn_memory_failure("relevance selection", exc)
        return _keyword_memory_matches(files, recent, max_items)

    selected: list[str] = []
    for index in indices:
        if isinstance(index, int) and 0 <= index < len(files):
            selected.append(files[index]["filename"])
            if len(selected) >= max_items:
                break
    return selected or _keyword_memory_matches(files, recent, max_items)


def load_memories(messages: list[dict[str, Any]]) -> str:
    selected_files = select_relevant_memories(messages)
    if not selected_files:
        return ""

    parts = ["<relevant_memories>"]
    for filename in selected_files:
        content = read_memory_file(filename)
        if content:
            parts.append(content)
    parts.append("</relevant_memories>")
    return "\n\n".join(parts)


def extract_memories(messages: list[dict[str, Any]]) -> None:
    dialogue_parts: list[str] = []
    for msg in messages[-10:]:
        role = msg.get("role", "?")
        content = content_to_text(msg.get("content", ""))
        if content.strip():
            dialogue_parts.append(f"{role}: {content}")
    dialogue = "\n".join(dialogue_parts)
    if not dialogue.strip():
        return

    existing = list_memory_files()
    existing_description = (
        "\n".join(f"- {item['name']}: {item['description']}" for item in existing)
        if existing
        else "(none)"
    )
    prompt = (
        "Extract user preferences, constraints, or project facts from this dialogue.\n"
        "Return a JSON array. Each item: {name, type, description, body}.\n"
        "- name: short kebab-case identifier (e.g. 'user-preference-tabs')\n"
        "- type: one of 'user' (user preference), 'feedback' (guidance), "
        "'project' (project fact), 'reference' (external pointer)\n"
        "- description: one-line summary for index lookup\n"
        "- body: full detail in markdown\n"
        "If nothing new or already covered by existing memories, return [].\n\n"
        f"Existing memories:\n{existing_description}\n\n"
        f"Dialogue:\n{dialogue[:4000]}"
    )

    try:
        items = _json_array_from_text(
            _completion_text(prompt, max_tokens=800),
            greedy=True,
        )
    except Exception as exc:
        _warn_memory_failure("extraction", exc)
        return

    count = 0
    for item in items:
        fields = _memory_fields(item)
        if fields is None:
            continue
        write_memory_file(*fields)
        count += 1
    if count:
        print(f"\n\033[33m[Memory: extracted {count} new memories]\033[0m")


def consolidate_memories() -> None:
    files = list_memory_files()
    if len(files) < CONSOLIDATE_THRESHOLD:
        return

    catalog = "\n\n".join(
        (
            f"## {item['filename']}\n"
            f"name: {item['name']}\n"
            f"description: {item['description']}\n"
            f"{item['body']}"
        )
        for item in files
    )
    prompt = (
        "Consolidate the following memory files. Rules:\n"
        "1. Merge duplicates into one\n"
        "2. Remove outdated/contradicted memories\n"
        "3. Keep the total under 30 memories\n"
        "4. Preserve important user preferences above all\n"
        "Return a JSON array. Each item: {name, type, description, body}.\n\n"
        f"{catalog[:16000]}"
    )

    try:
        items = _json_array_from_text(
            _completion_text(prompt, max_tokens=3000),
            greedy=True,
        )
    except Exception as exc:
        _warn_memory_failure("consolidation", exc)
        return

    for path in MEMORY_DIR.glob("*.md"):
        if path.name != "MEMORY.md":
            path.unlink()

    count = 0
    for item in items:
        fields = _memory_fields(item)
        if fields is None:
            continue
        write_memory_file(*fields)
        count += 1

    print(f"\n\033[33m[Memory: consolidated {len(files)} → {count} memories]\033[0m")
