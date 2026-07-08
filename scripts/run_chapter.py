from pathlib import Path
import runpy
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_chapter.py s01_agent_loop")

    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    chapter_dir = (project_root / "chapters" / sys.argv[1]).resolve()
    candidates = [chapter_dir / "main.py", chapter_dir / "code.py"]
    chapter = next((path for path in candidates if path.exists()), None)
    if chapter is None:
        expected = " or ".join(str(path) for path in candidates)
        raise SystemExit(f"chapter not found: {expected}")

    chapter_path = str(chapter_dir)
    src_path = str(src_dir)
    sys.path.insert(0, src_path)
    sys.path.insert(0, chapter_path)
    try:
        runpy.run_path(str(chapter), run_name="__main__")
    finally:
        if chapter_path in sys.path:
            sys.path.remove(chapter_path)
        if src_path in sys.path:
            sys.path.remove(src_path)


if __name__ == "__main__":
    main()
