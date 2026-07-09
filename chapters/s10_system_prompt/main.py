from agent import agent_loop
from hook import (
    context_inject_hook,
    large_output_hook,
    log_hook,
    permission_hook,
    register_hook,
    summary_hook,
    trigger_hooks,
)
from system_prompt import system_message, update_context
from util.client import end_client

import subagent  # Registers the parent-only task tool.


def register_default_hooks() -> None:
    register_hook("UserPromptSubmit", context_inject_hook)
    register_hook("PreToolUse", permission_hook)
    register_hook("PreToolUse", log_hook)
    register_hook("PostToolUse", large_output_hook)
    register_hook("Stop", summary_hook)


def main() -> None:
    messages = [system_message()]
    register_default_hooks()

    while True:
        try:
            query = input(">> ")
            replacement = trigger_hooks("UserPromptSubmit", query)
            if replacement is not None:
                query = replacement
            messages.append({"role": "user", "content": query})
            messages = agent_loop(messages, max_turns=100)
        except KeyboardInterrupt:
            end_client()
            break
        except EOFError:
            break


if __name__ == "__main__":
    main()
