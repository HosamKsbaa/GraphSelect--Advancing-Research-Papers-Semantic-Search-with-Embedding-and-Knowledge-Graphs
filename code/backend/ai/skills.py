"""On-demand capability skill loader (`load_skill`) for the ALRS Research Agent (M4).

Reads `ai/capabilities/<skill>/SKILL.md` files only when requested by the active
agent stage, keeping unrelated instructions out of the prompt context.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

CAPABILITIES_DIR = Path(__file__).resolve().parent / "capabilities"

_SKILL_ALIASES: dict[str, str] = {
    "search-literature": "search_literature",
    "search_literature": "search_literature",
    "literature-search": "search_literature",
    "literature_search": "search_literature",
    "write-literature-review": "write_literature_review",
    "write_literature_review": "write_literature_review",
    "evidence-review": "write_literature_review",
    "evidence_review": "write_literature_review",
    "verify-citations": "verify_citations",
    "verify_citations": "verify_citations",
    "citation-export": "verify_citations",
    "citation_export": "verify_citations",
    "collection-curator": "collection_curator",
    "collection_curator": "collection_curator",
}


class SkillMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    folder: str
    description: str
    aliases: list[str] = Field(default_factory=list)


class LoadedSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    folder: str
    description: str
    instructions: str


def _parse_skill_markdown(text: str, default_name: str) -> tuple[str, str, str]:
    lines = text.strip().splitlines()
    name = default_name
    description = ""
    body_start = 0
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            line = lines[idx].strip()
            if line == "---":
                body_start = idx + 1
                break
            if ":" in line:
                key, val = line.split(":", 1)
                k = key.strip().lower()
                v = val.strip()
                if k == "name":
                    name = v
                elif k == "description":
                    description = v
    body = "\n".join(lines[body_start:]).strip()
    return name, description, body


def list_available_skills(
    capabilities_dir: Path = CAPABILITIES_DIR,
) -> list[SkillMetadata]:
    """List all installed capability skills with their descriptions and aliases."""
    skills: list[SkillMetadata] = []
    if not capabilities_dir.exists():
        return skills
    for skill_md in sorted(capabilities_dir.glob("*/SKILL.md")):
        folder = skill_md.parent.name
        name, description, _ = _parse_skill_markdown(
            skill_md.read_text(encoding="utf-8"),
            default_name=folder.replace("_", "-"),
        )
        aliases = sorted(
            alias for alias, target in _SKILL_ALIASES.items() if target == folder
        )
        skills.append(
            SkillMetadata(
                name=name,
                folder=folder,
                description=description,
                aliases=aliases,
            )
        )
    return skills


def load_skill(
    skill_name: str,
    capabilities_dir: Path = CAPABILITIES_DIR,
) -> LoadedSkill:
    """Load a capability skill's full Markdown instructions on demand."""
    normalized = skill_name.strip().lower()
    folder = _SKILL_ALIASES.get(normalized, normalized.replace("-", "_"))
    skill_path = capabilities_dir / folder / "SKILL.md"
    if not skill_path.exists():
        available = [s.name for s in list_available_skills(capabilities_dir)]
        raise KeyError(
            f"Unknown skill '{skill_name}'. Available skills: {', '.join(available)}"
        )
    raw = skill_path.read_text(encoding="utf-8")
    name, description, body = _parse_skill_markdown(
        raw, default_name=folder.replace("_", "-")
    )
    return LoadedSkill(
        name=name,
        folder=folder,
        description=description,
        instructions=body,
    )
