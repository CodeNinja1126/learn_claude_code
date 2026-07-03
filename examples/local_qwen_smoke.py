from utill.client import create_client
from utill.config import load_config


def main() -> None:
    config = load_config()
    client = create_client(config)
    response = client.chat.completions.create(
        model=config.model,
        messages=[{"role": "user", "content": "Say hello in one short sentence."}],
    )
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
