from util.client import create_client
from util.config import load_config


def main() -> None:
    config = load_config()
    client = create_client(config)
    response = client.chat.completions.create(
        model=config.model,
        messages=[{"role": "user", "content": "Return the word ok."}],
    )
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
