from util.config import load_config


def test_load_config_defaults() -> None:
    config = load_config()
    assert config.base_url
    assert config.api_key
    assert config.model
