from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FileRole(str, Enum):
    INSTRUCTIONS = "instructions"
    SKILL = "skill"
    PROMPT = "prompt"
    AGENT = "agent"
    OTHER = "other"


@dataclass
class ParsedFile:
    """A single markdown file discovered under .claude/ (or equivalent)."""

    path: Path
    relative_path: str
    role: FileRole
    raw_text: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    frontmatter_valid: bool = True
    frontmatter_error: str | None = None

    total_tokens: int = 0
    frontmatter_tokens: int = 0
    body_tokens: int = 0
    description_tokens: int | None = None

    @property
    def description(self) -> str | None:
        value = self.frontmatter.get("description")
        return value if isinstance(value, str) else None

    @property
    def name(self) -> str | None:
        value = self.frontmatter.get("name")
        return value if isinstance(value, str) else None


INSUFFICIENT_MIN_SKILLS = 3
INSUFFICIENT_MIN_BODY_TOKENS = 1000


@dataclass
class ScanResult:
    root: Path
    files: list[ParsedFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cursor_sibling_files: int = 0  # count of .mdc files in a sibling .cursor/rules/ if present

    @property
    def total_tokens(self) -> int:
        return sum(f.total_tokens for f in self.files)

    @property
    def skill_body_tokens(self) -> int:
        """Sum of body tokens across SKILL.md files only."""
        return sum(f.body_tokens for f in self.files if f.role is FileRole.SKILL)

    @property
    def is_insufficient(self) -> bool:
        """True when there isn't enough skill content for grading to be meaningful.

        Trips on EITHER condition (per re-test feedback): fewer than
        ``INSUFFICIENT_MIN_SKILLS`` SKILL.md files OR fewer than
        ``INSUFFICIENT_MIN_BODY_TOKENS`` aggregate body tokens across
        skills. Using OR (not AND) catches both the "too-few placeholder
        skills" and the "few-tiny-files" failure modes that v0.1.0
        misled with a trivial A+.
        """
        skill_files = self.by_role(FileRole.SKILL)
        return (
            len(skill_files) < INSUFFICIENT_MIN_SKILLS
            or self.skill_body_tokens < INSUFFICIENT_MIN_BODY_TOKENS
        )

    @property
    def total_files(self) -> int:
        return len(self.files)

    def by_role(self, role: FileRole) -> list[ParsedFile]:
        return [f for f in self.files if f.role == role]
