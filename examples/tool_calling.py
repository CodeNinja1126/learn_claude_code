from utill.client import create_client
from utill.config import load_config
from utill.loop import AgentLoop
from utill.tools import TOOL_HANDLERS, TOOLS


def main() -> None:
    config = load_config()
    loop = AgentLoop(create_client(config), config, TOOLS, TOOL_HANDLERS)
    answer = loop.run(
        [{"role": "user", "content": "List the files in the current directory."}]
    )
    print(answer)


if __name__ == "__main__":
    main()
