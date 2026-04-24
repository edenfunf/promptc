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


@dataclass
class ScanResult:
    root: Path
    files: list[ParsedFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(f.total_tokens for f in self.files)

    @property
    def total_files(self) -> int:
        return len(self.files)

    def by_role(self, role: FileRole) -> list[ParsedFile]:
        return [f for f in self.files if f.role == role]
