"""Walk a directory and classify discovered markdown files by role.

The scanner is intentionally conservative:
- Follows no symlinks (avoids cycles)
- Reads only `.md` and `.mdc` files
- Skips dotfiles and common ignore directories
- Classifies by directory pattern relative to the scan root

Role classification (relative to scan root):
    CLAUDE.md or AGENTS.md at root         -> INSTRUCTIONS
    skills/<name>/SKILL.md                 -> SKILL          (entrypoint)
    skills/<name>.md                       -> SKILL          (flat layout)
    skills/<name>/<anything else>.md       -> OTHER          (support file)
    commands/*.md                          -> PROMPT
    agents/*.md                            -> AGENT
    anything else                          -> OTHER

Why supporting files inside a skill directory are OTHER, not SKILL:
    The Claude Code Skills documentation defines SKILL.md as the skill's
    required entrypoint; other files in the directory are optional
    templates / examples / scripts / reference material that load only
    when the skill body references them. Counting them as SKILL files
    inflates the exposure multiplier because their worst-case tokens
    are large while their promised tokens are zero (they have no
    frontmatter of their own).
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable
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
        # `skills/<name>/SKILL.md` is the entrypoint; flat `skills/<name>.md`
        # also counts. Everything else under `skills/**` is a support file.
        if name.lower() == "skill.md":
            return FileRole.SKILL
        try:
            skills_idx = relative_parts.index("skills")
        except ValueError:
            skills_idx = 0
        if len(relative_parts) - skills_idx == 2:
            return FileRole.SKILL
        return FileRole.OTHER
    if "commands" in relative_parts:
        return FileRole.PROMPT
    if "agents" in relative_parts:
        return FileRole.AGENT

    return FileRole.OTHER


def resolve_scan_root(path: Path) -> Path:
    """If `path` contains a `.claude/` subdir, scan that. Otherwise scan path itself."""
    claude_dir = path / ".claude"
    return claude_dir if claude_dir.is_dir() else path


def _is_excluded(relative_display: str, patterns: tuple[str, ...]) -> bool:
    """Return True if the POSIX-style relative path matches any glob pattern.

    Patterns use fnmatch semantics (``*`` matches within a segment, not across
    ``/``; use ``**`` to cross segments). Matching is tried against the full
    path and against the basename, so ``--exclude README.md`` works even when
    the file lives deep in a tree.
    """
    if not patterns:
        return False
    basename = relative_display.rsplit("/", 1)[-1]
    for pattern in patterns:
        if fnmatch.fnmatch(relative_display, pattern):
            return True
        if fnmatch.fnmatch(basename, pattern):
            return True
    return False


def scan(path: Path, *, excludes: Iterable[str] = ()) -> ScanResult:
    """Walk `path` and return a ScanResult populated with parsed files and warnings.

    ``excludes`` is an optional iterable of fnmatch-style glob patterns applied
    to the POSIX relative path (or basename) of each candidate file.
    """
    root = resolve_scan_root(path).resolve()
    result = ScanResult(root=root)
    exclude_patterns = tuple(excludes)

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

            if _is_excluded(relative_display, exclude_patterns):
                continue

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
