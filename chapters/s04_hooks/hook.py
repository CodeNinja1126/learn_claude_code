from utill import WORKDIR

HOOKS = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": [],
}

DENY_LIST = [
    "rm -rf /",
    "sudo",
    "shutdown",
    "reboot",
    "mkfs",
    "dd if=",
    "> /dev/sda",
]

PERMISSION_RULES = [
    {
        "tools": ["write_files", "edit_files"],
        "check": lambda args: not (WORKDIR / args.get("path", ""))
        .resolve()
        .is_relative_to(WORKDIR),
        "message": "Writing outside workspace",
    },
    {
        "tools": ["bash"],
        "check": lambda args: any(
            kw in args.get("command", "") for kw in ["rm ", "> /etc/", "chmod 777"]
        ),
        "message": "Potentially destructive command",
    },
]


def register_hook(event: str, callback):
    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result

    return None


def context_inject_hook(query: str) -> str | None:
    """Inject current working directory info into every prompt."""
    print(f"\033[90m[HOOK] UserPromptSubmit: working in {WORKDIR}\033[0m")
    return None  # return None = no modification, let prompt through


def check_deny_list(command: str) -> str | None:
    for pattern in DENY_LIST:
        if pattern in command:
            return f"Blocked: '{pattern}' is on the deny list"
    return None


def check_rules(tool_name: str, args: dict) -> str | None:
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    return None


def ask_user(tool_name: str, args: dict, reason: str) -> str:
    print(f"\n⚠  {reason}")
    print(f"    Tool: {tool_name}({args})")
    choice = input("   Allow? [Y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


def permission_hook(name: str, args: dict | None = None):
    if name == "bash":
        reason = check_deny_list(args["command"])
        if reason:
            print(f"\n⛔ {reason}")
            return "Permission denied by deny list."

    reason = check_rules(name, args)
    if reason:
        decision = ask_user(name, args, reason)
        if decision == "deny":
            return "Permission denied by user."
    return None


def log_hook(name: str, args: dict):
    print(f"[HOOK] {name} 사용되었음.")


def large_output_hook(name: str, output):
    if len(str(output)) > 100000:
        print(f"[HOOK] ⚠ Large output from {name}")


def summary_hook(messages: list) -> str | None:
    """Print a summary when the loop is about to stop."""
    tool_count = sum(
        1
        if m['role'] == 'tool' else 0 for m in messages
    )
    print(f"\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None  # return None = allow stop, return string = force continuation
