from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ModelConfig:
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "qwen-local"
    model: str = "qwen3.6"


def load_config() -> ModelConfig:
    return ModelConfig(
        base_url=os.getenv("OPENAI_BASE_URL", ModelConfig.base_url),
        api_key=os.getenv("OPENAI_API_KEY", ModelConfig.api_key),
        model=os.getenv("QWEN_MODEL", ModelConfig.model),
    )
