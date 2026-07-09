from typing import Any
import json

from memory_store import read_memory_index
from messages import INSTRUCTION_ROLES
from skill import list_skills
from tool import TOOL_HANDLERS
from util import WORKDIR


PROMPT_SECTIONS = {
    "identity": "You are a coding agent. Act, don't explain.",
    "tools": "Available tools: {tools}.",
    "workspace": "Working directory: {workspace}",
    "memory": "Relevant memories:\n{memories}",
}

_last_context_key: str | None = None
_last_prompt: str | None = None


def assemble_system_prompt(context: dict[str, Any]) -> str:
    sections = [PROMPT_SECTIONS["identity"]]

    tools_section = PROMPT_SECTIONS["tools"].format(
        tools=", ".join(context.get("enabled_tools", []))
    )
    skills = context.get("skills", "")
    if skills:
        tools_section = (
            f"{tools_section}\n\n"
            f"Skills available:\n{skills}\n"
            "Use load_skill to get full details when needed."
        )
    sections.append(tools_section)
    sections.append(
        PROMPT_SECTIONS["workspace"].format(
            workspace=context.get("workspace", str(WORKDIR))
        )
    )

    memories = context.get("memories", "")
    if memories:
        sections.append(PROMPT_SECTIONS["memory"].format(memories=memories))
    sections.append(
        "Relevant memories may also be injected per request. "
        "Respect user preferences from memory.\n"
        "When the user says 'remember' or expresses a clear preference, extract it as a memory."
    )

    return "\n\n".join(sections)


def get_system_prompt(context: dict[str, Any]) -> str:
    global _last_context_key, _last_prompt

    key = json.dumps(context, sort_keys=True, ensure_ascii=False, default=str)
    if key == _last_context_key and _last_prompt:
        print("  \033[90m[cache hit] system prompt unchanged\033[0m")
        return _last_prompt

    _last_context_key = key
    _last_prompt = assemble_system_prompt(context)

    loaded = ["identity", "tools", "workspace"]
    if context.get("memories"):
        loaded.append("memory")
    print(f"  \033[32m[assembled] sections: {', '.join(loaded)}\033[0m")
    return _last_prompt


def update_context(
    context: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "enabled_tools": list(TOOL_HANDLERS.keys()),
        "workspace": str(WORKDIR),
        "skills": list_skills(),
        "memories": read_memory_index(),
    }


def system_message(context: dict[str, Any] | None = None) -> dict[str, str]:
    if context is None:
        context = update_context({}, [])
    return {"role": "developer", "content": get_system_prompt(context)}


def with_system_message(
    messages: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if context is None:
        context = update_context({}, messages)
    return [
        system_message(context),
        *[
            msg
            for msg in messages
            if not (isinstance(msg, dict) and msg.get("role") in INSTRUCTION_ROLES)
        ],
    ]
