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

import json

SYSTEM = f"너는 디렉토리 {WORKDIR}의 코딩 에이전트야. 도구를 활용해 문제를 해결해."

def agent_loop(
    messages: list[dict[str, any]],
    max_turns: int = 8,
):

    config = load_config()
    client = create_client(config)

    for _ in range(max_turns):

        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            tools=TOOLS,
        )

        message = response.choices[0].message
        messages.append({'role': 'assistant', 'content': message.content})
        print(message.content)
        if not message.tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            return messages

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            blocked = trigger_hooks('PreToolUse', tool_name, tool_args)
            if blocked:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": blocked,
                    }
                )
                print("permission_denied")
                continue
            result = TOOL_HANDLERS[tool_name](**tool_args)
            trigger_hooks("PostToolUse", tool_name, result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )


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
            trigger_hooks("UserPromptSubmit", query)
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


if __name__ == "__main__":
    main()
