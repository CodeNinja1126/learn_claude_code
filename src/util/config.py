from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ModelConfig:
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "qwen3.6-local"
    model: str = "qwen3.6"


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            values[key] = value
    return values


def _project_env() -> dict[str, str]:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        return _parse_env_file(env_file)
    return _parse_env_file(PROJECT_ROOT / ".env.example")


def _get_config_value(name: str, fallback: str, file_env: dict[str, str]) -> str:
    return os.getenv(name) or file_env.get(name) or fallback


def load_config() -> ModelConfig:
    file_env = _project_env()
    return ModelConfig(
        base_url=_get_config_value("OPENAI_BASE_URL", ModelConfig.base_url, file_env),
        api_key=_get_config_value("OPENAI_API_KEY", ModelConfig.api_key, file_env),
        model=_get_config_value("QWEN_MODEL", ModelConfig.model, file_env),
    )
