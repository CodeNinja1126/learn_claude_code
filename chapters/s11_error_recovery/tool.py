from typing import Any, Iterable
import ast
import glob
import json
import os
import subprocess
from pathlib import Path

from skill import SKILL_REGISTRY
from util import WORKDIR


def _function_tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters["required"] = required
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


TOOLS = [
    _function_tool(
        "bash",
        "Run a shell command.",
        {"command": {"type": "string"}},
        ["command"],
    ),
    _function_tool(
        "read_file",
        "Read file contents.",
        {
            "path": {"type": "string"},
            "limit": {"type": "integer"},
        },
        ["path"],
    ),
    _function_tool(
        "write_file",
        "Write content to a file.",
        {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        ["path", "content"],
    ),
    _function_tool(
        "edit_file",
        "Replace exact text in a file once.",
        {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        ["path", "old_text", "new_text"],
    ),
    _function_tool(
        "glob",
        "Find files matching a glob pattern.",
        {"pattern": {"type": "string"}},
        ["pattern"],
    ),
    _function_tool(
        "todo_write",
        (
            "Plan and track multi-step coding work. Use this before starting any task "
            "that requires multiple steps, file changes, investigation, or a subtask; "
            "keep exactly one item in_progress and update statuses as work progresses."
        ),
        {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                    },
                    "required": ["content", "status"],
                },
            },
        },
        ["todos"],
    ),
    _function_tool(
        "load_skill",
        "Load the full content of a skill by name.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _function_tool(
        "compact",
        "Summarize earlier conversation to free context space.",
        {"focus": {"type": "string"}},
    ),
]


def tool_subset(
    names: Iterable[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected = set(names)
    tools = [tool for tool in TOOLS if tool["function"]["name"] in selected]
    handlers = {name: TOOL_HANDLERS[name] for name in names}
    return tools, handlers


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(pattern in command for pattern in dangerous):
        return "Error: Dangerous command blocked"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        return output[:50000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as exc:
        return f"Error: {exc}"


def safe_path(path: str) -> Path:
    resolved = (WORKDIR / path).resolve()
    if not resolved.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {path}")
    return resolved


def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text()
        if old_text not in text:
            return f"Error: text not found in {path}"
        file_path.write_text(text.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_glob(pattern: str) -> str:
    try:
        results = []
        for match in glob.glob(pattern, root_dir=WORKDIR):
            path = (WORKDIR / match).resolve()
            if path.is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "(no matches)"
    except Exception as exc:
        return f"Error: {exc}"


def load_skill(name: str) -> str:
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        return f"Skill not found: {name}"
    return skill["content"]


CURRENT_TODOS: list[dict[str, Any]] = []


def _normalize_todos(todos: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "Error: todos must be a list or JSON array string"
    if not isinstance(todos, list):
        return None, "Error: todos must be a list"
    for index, item in enumerate(todos):
        if not isinstance(item, dict):
            return None, f"Error: todos[{index}] must be an object"
        if "content" not in item or "status" not in item:
            return None, f"Error: todos[{index}] missing 'content' or 'status'"
        if item["status"] not in ("pending", "in_progress", "completed"):
            return None, f"Error: todos[{index}] has invalid status '{item['status']}'"
    return todos, None


def run_todo_write(todos: list[dict[str, Any]]) -> str:
    global CURRENT_TODOS

    normalized, error = _normalize_todos(todos)
    if error:
        return error
    CURRENT_TODOS = normalized or []

    lines = ["\n\033[33m## Current Tasks\033[0m"]
    for item in CURRENT_TODOS:
        icon = {
            "pending": " ",
            "in_progress": "\033[36m▸\033[0m",
            "completed": "\033[32m✓\033[0m",
        }[item["status"]]
        lines.append(f"  [{icon}] {item['content']}")
    print("\n".join(lines))
    return f"Updated {len(CURRENT_TODOS)} tasks"


TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
    "todo_write": run_todo_write,
    "load_skill": load_skill,
}
