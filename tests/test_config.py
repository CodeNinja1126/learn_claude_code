import util.config as config_module
from util.config import load_config


def test_load_config_defaults() -> None:
    config = load_config()
    assert config.base_url
    assert config.api_key
    assert config.model


def test_load_config_reads_project_env_example(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_MODEL", raising=False)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env.example").write_text(
        "\n".join(
            [
                "OPENAI_BASE_URL=http://example.local/v1",
                "OPENAI_API_KEY=example-key",
                "QWEN_MODEL=example-model",
            ]
        )
    )

    config = load_config()

    assert config.base_url == "http://example.local/v1"
    assert config.api_key == "example-key"
    assert config.model == "example-model"


def test_load_config_prefers_env_over_env_example(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env.example").write_text(
        "\n".join(
            [
                "OPENAI_BASE_URL=http://example.local/v1",
                "OPENAI_API_KEY=example-key",
                "QWEN_MODEL=example-model",
            ]
        )
    )
    monkeypatch.setenv("QWEN_MODEL", "shell-model")

    config = load_config()

    assert config.model == "shell-model"
    assert config.base_url == "http://example.local/v1"
