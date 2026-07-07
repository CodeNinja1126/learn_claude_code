from pathlib import Path


def list_files(path: str = ".") -> str:
    root = Path(path).resolve()
    if not root.exists():
        return f"{root} does not exist"
    if root.is_file():
        return str(root)
    return "\n".join(str(item) for item in sorted(root.iterdir()))


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")
