from util.tools.filesystem import list_files, read_text
from util.tools.shell import run_command


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text",
            "description": "Read a UTF-8 text file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command."}
                },
                "required": ["command"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "list_files": list_files,
    "read_text": read_text,
    "run_command": run_command,
}
