from typing import Any

from frontmatter import parse_frontmatter
from util import WORKDIR


SKILLS_DIR = WORKDIR / "skills"
SKILL_REGISTRY: dict[str, dict[str, Any]] = {}


def _scan_skills() -> None:
    if not SKILLS_DIR.exists():
        return
    for path in sorted(SKILLS_DIR.iterdir()):
        if not path.is_dir():
            continue
        manifest = path / "SKILL.md"
        if not manifest.exists():
            continue
        raw = manifest.read_text()
        meta, _ = parse_frontmatter(raw)
        name = meta.get("name", path.name)
        description = meta.get("description", raw.split("\n")[0].lstrip("#").strip())
        SKILL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "content": raw,
        }


def list_skills() -> str:
    return "\n".join(
        f"- **{skill['name']}**: {skill['description']}"
        for skill in SKILL_REGISTRY.values()
    )


_scan_skills()
