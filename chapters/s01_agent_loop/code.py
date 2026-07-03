from utill.client import create_client
from utill.config import load_config

import os
import subprocess
import json


SYSTEM = f"너는 디렉토리 {os.getcwd()}의 코딩 에이전트야. bash를 활용해 문제를 해결해."


TOOLS = [{
        "name": "bash",
        "description": "Run a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        }
    }
]

def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=os.getcwd(),
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"


def agent_loop(
        messages: list[dict[str, any]],
        max_turns: int = 8,
    ):

    config = load_config()
    client = create_client(config)

    messages = [{"role": "system", "content": SYSTEM}] + messages

    for _ in range(max_turns):

        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            tools=TOOLS,
        )

        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        print(message.content)
        if not message.tool_calls:
            return None
        
        for tool_call in message.tool_calls:
            if tool_call.function.name == "bash":
                try:
                    args = json.loads(tool_call.function.arguments)
                    command = args.get("command", "")
                except json.JSONDEcodeError:
                    command = ""
                print(f"\033[33m$ {command}\033[0m")
                result = run_bash(command)
                print(result)
                messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )


def main() -> None:

    messages = [{"role": "user", "content": "Hello World! 를 출력하는 C 코드 파일 하나 만들어줘."}]
    agent_loop(messages)

if __name__ == "__main__":
    main()
