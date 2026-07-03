from pathlib import Path
import runpy
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_chapter.py s01_agent_loop")

    chapter = Path("chapters") / sys.argv[1] / "code.py"
    if not chapter.exists():
        raise SystemExit(f"chapter not found: {chapter}")
    runpy.run_path(str(chapter), run_name="__main__")


if __name__ == "__main__":
    main()
