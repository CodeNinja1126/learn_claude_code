from utill.client import create_client
from utill.config import load_config


def main() -> None:
    config = load_config()
    client = create_client(config)
    messages = [{"role": "user", "content": "Explain what an agent harness is."}]
    response = client.chat.completions.create(model=config.model, messages=messages)
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
