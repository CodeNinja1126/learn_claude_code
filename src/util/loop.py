from collections.abc import Callable, Sequence
import json
from typing import Any

from openai import OpenAI

from util.config import ModelConfig, load_config


ToolHandler = Callable[..., str]


class AgentLoop:
    def __init__(
        self,
        client: OpenAI,
        config: ModelConfig | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        handlers: dict[str, ToolHandler] | None = None,
    ) -> None:
        self.client = client
        self.config = config or load_config()
        self.tools = list(tools or [])
        self.handlers = handlers or {}

    def run(self, messages: list[dict[str, Any]], max_turns: int = 8) -> str:
        for _ in range(max_turns):
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                tools=self.tools or None,
            )
            message = response.choices[0].message
            messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                return message.content or ""

            for tool_call in message.tool_calls:
                handler = self.handlers[tool_call.function.name]
                arguments = json.loads(tool_call.function.arguments or "{}")
                result = handler(**arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        raise RuntimeError(f"agent loop exceeded {max_turns} turns")
