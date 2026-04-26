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
    """Given a path relative to the scan root (POSIX parts), return its role.

    Classification priority:
      1. Filename-based: any file literally named ``SKILL.md`` (case-insensitive)
         is a SKILL, regardless of where it lives. This catches the case
         where the user points promptc at the inside of a skills tree
         (e.g. ``promptc analyze /path/to/anthropics-skills/skills``)
         where the relative paths no longer contain the ``skills/`` segment.
      2. Root-level instruction files: ``CLAUDE.md`` / ``AGENTS.md`` at root.
      3. Path-based: ``skills/foo.md`` flat layout, ``commands/*``, ``agents/*``.
      4. Anything else, including non-SKILL.md files inside ``skills/<name>/``,
         is OTHER (support material — templates, references, examples).
    """
    if not relative_parts:
        return FileRole.OTHER

    name = relative_parts[-1]

    # Priority 1: SKILL.md is a skill regardless of parent path.
    if name.lower() == "skill.md":
        return FileRole.SKILL

    # Priority 2: root-level instruction files.
    if len(relative_parts) == 1 and name in INSTRUCTION_FILES:
        return FileRole.INSTRUCTIONS

    # Priority 3: path-based fallback for non-SKILL.md files.
    if "skills" in relative_parts:
        skills_idx = relative_parts.index("skills")
        # Flat layout: `skills/foo.md` (exactly one segment after `skills/`).
        if len(relative_parts) - skills_idx == 2:
            return FileRole.SKILL
        # Anything else under `skills/**` is support material.
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


def _count_cursor_sibling(original_path: Path, scan_root: Path) -> int:
    """Count .mdc files in a sibling `.cursor/rules/` directory, if present.

    Cursor's rule format lives in `.cursor/rules/*.mdc`. promptc v0.1 doesn't
    walk it (Cursor support is v0.2 work, tracked separately), but if such a
    directory exists next to the .claude/ being scanned, surface that fact so
    the user knows the bulk of their AI context wasn't audited.

    Returns 0 if no sibling `.cursor/rules/` exists.
    """
    # The "sibling" is relative to the user-specified path, not the resolved
    # `.claude/` subdir. If the user pointed at /proj and we resolved to
    # /proj/.claude, the cursor sibling is /proj/.cursor/.
    if scan_root != original_path and scan_root.name == ".claude":
        candidate_parent = original_path
    else:
        candidate_parent = scan_root.parent if scan_root.name == ".claude" else original_path

    cursor_rules = candidate_parent / ".cursor" / "rules"
    if not cursor_rules.is_dir():
        return 0
    try:
        return sum(
            1 for p in cursor_rules.rglob("*.mdc") if p.is_file()
        )
    except OSError:
        return 0


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
    result.cursor_sibling_files = _count_cursor_sibling(path, root)
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
            relative = file_path.relative_to(root)

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
