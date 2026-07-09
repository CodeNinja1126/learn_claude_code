from typing import Any

from frontmatter import parse_frontmatter
from util import WORKDIR


MEMORY_DIR = WORKDIR / ".memory"
MEMORY_DIR.mkdir(exist_ok=True)
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"


def write_memory_file(name: str, mem_type: str, description: str, body: str):
    slug = name.lower().replace(" ", "-").replace("/", "-")
    path = MEMORY_DIR / f"{slug}.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\ntype: {mem_type}\n---\n\n{body}\n"
    )
    rebuild_memory_index()
    return path


def rebuild_memory_index() -> None:
    lines: list[str] = []
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if path.name == "MEMORY.md":
            continue
        raw = path.read_text()
        meta, body = parse_frontmatter(raw)
        name = meta.get("name", path.stem)
        description = meta.get("description", body.split("\n")[0][:80])
        lines.append(f"- [{name}]({path.name}) — {description}")
    MEMORY_INDEX.write_text("\n".join(lines) + "\n" if lines else "")


def read_memory_index() -> str:
    if not MEMORY_INDEX.exists():
        return ""
    return MEMORY_INDEX.read_text().strip()


def read_memory_file(filename: str) -> str | None:
    path = MEMORY_DIR / filename
    if not path.exists():
        return None
    return path.read_text()


def list_memory_files() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if path.name == "MEMORY.md":
            continue
        raw = path.read_text()
        meta, body = parse_frontmatter(raw)
        result.append(
            {
                "filename": path.name,
                "name": meta.get("name", path.stem),
                "description": meta.get("description", ""),
                "type": meta.get("type", "user"),
                "body": body,
            }
        )
    return result
