"""Walk a directory and classify discovered markdown files by role.

The scanner is intentionally conservative:
- Follows no symlinks (avoids cycles)
- Reads only `.md` and `.mdc` files
- Skips dotfiles and common ignore directories
- Classifies by directory pattern relative to the scan root

Role classification (relative to scan root):
    CLAUDE.md or AGENTS.md at root         -> INSTRUCTIONS
    skills/<name>/SKILL.md                 -> SKILL
    skills/<name>.md                       -> SKILL
    commands/*.md                          -> PROMPT
    agents/*.md                            -> AGENT
    anything else                          -> OTHER
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from promptc.models import FileRole, ScanResult
from promptc.parser import parse_file

MD_EXTENSIONS = {".md", ".mdc"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}

INSTRUCTION_FILES = {"CLAUDE.md", "AGENTS.md"}


def classify(relative_parts: tuple[str, ...]) -> FileRole:
    """Given a path relative to the scan root (POSIX parts), return its role."""
    if not relative_parts:
        return FileRole.OTHER

    name = relative_parts[-1]

    if len(relative_parts) == 1 and name in INSTRUCTION_FILES:
        return FileRole.INSTRUCTIONS

    if "skills" in relative_parts:
        return FileRole.SKILL
    if "commands" in relative_parts:
        return FileRole.PROMPT
    if "agents" in relative_parts:
        return FileRole.AGENT

    return FileRole.OTHER


def resolve_scan_root(path: Path) -> Path:
    """If `path` contains a `.claude/` subdir, scan that. Otherwise scan path itself."""
    claude_dir = path / ".claude"
    return claude_dir if claude_dir.is_dir() else path


def scan(path: Path) -> ScanResult:
    """Walk `path` and return a ScanResult populated with parsed files and warnings."""
    root = resolve_scan_root(path).resolve()
    result = ScanResult(root=root)

    if not root.exists():
        result.warnings.append(f"path does not exist: {root}")
        return result
    if not root.is_dir():
        result.warnings.append(f"path is not a directory: {root}")
        return result

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

        for filename in filenames:
            if filename.startswith("."):
                continue
            ext = Path(filename).suffix.lower()
            if ext not in MD_EXTENSIONS:
                continue

            file_path = Path(dirpath) / filename
            try:
                relative = file_path.relative_to(root)
            except ValueError:
                continue

            rel_parts = tuple(PurePosixPath(relative.as_posix()).parts)
            relative_display = relative.as_posix()
            role = classify(rel_parts)

            try:
                parsed = parse_file(file_path, relative_display, role)
            except OSError as exc:
                result.warnings.append(f"could not read {relative_display}: {exc}")
                continue

            if not parsed.frontmatter_valid and parsed.frontmatter_error:
                result.warnings.append(
                    f"{relative_display}: {parsed.frontmatter_error}"
                )

            result.files.append(parsed)

    result.files.sort(key=lambda f: f.relative_path)
    return result
