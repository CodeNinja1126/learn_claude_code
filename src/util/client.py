from openai import OpenAI

from util.config import ModelConfig, load_config

import requests


def create_client(config: ModelConfig | None = None) -> OpenAI:
    config = config or load_config()
    return OpenAI(base_url=config.base_url, api_key=config.api_key)


def end_client(config: ModelConfig | None = None):
    config = config or load_config()
    requests.post(
        config.base_url[:-2] + "api/chat",
        json={"model": config.model, "keep_alive": 0}
    )