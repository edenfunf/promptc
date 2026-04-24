"""Parse markdown files with optional YAML frontmatter.

Frontmatter format (Claude Skills, Cursor rules, etc.):

    ---
    name: skill-name
    description: one-line summary
    ---
    # Body starts here
    ...

This module returns the split components and leaves downstream
consumers responsible for interpretation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from promptc.models import FileRole, ParsedFile
from promptc.tokens import count_tokens

FRONTMATTER_DELIMITER = "---"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, str, bool, str | None]:
    """Split a markdown document into (frontmatter_dict, frontmatter_raw, body, valid, error).

    - If no leading `---` delimiter, returns ({}, "", text, True, None).
    - If delimiters are present but YAML is malformed, returns ({}, raw, body, False, error_msg).
    - `frontmatter_raw` includes the delimiter lines so token counts reflect the
      full cost of the frontmatter block in the source file.
    """
    if not text.startswith(FRONTMATTER_DELIMITER):
        return {}, "", text, True, None

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != FRONTMATTER_DELIMITER:
        return {}, "", text, True, None

    closing_index: int | None = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == FRONTMATTER_DELIMITER:
            closing_index = i
            break

    if closing_index is None:
        return {}, "", text, True, None

    frontmatter_raw = "".join(lines[: closing_index + 1])
    body = "".join(lines[closing_index + 1 :])
    yaml_body = "".join(lines[1:closing_index])

    try:
        data = yaml.safe_load(yaml_body) or {}
        if not isinstance(data, dict):
            return (
                {},
                frontmatter_raw,
                body,
                False,
                f"frontmatter did not parse as a mapping (got {type(data).__name__})",
            )
        return data, frontmatter_raw, body, True, None
    except yaml.YAMLError as exc:
        return {}, frontmatter_raw, body, False, f"YAML parse error: {exc}"


def _read_text(path: Path) -> str:
    """Read a text file, tolerating UTF-8 BOM and falling back for bad bytes."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def parse_file(path: Path, relative_path: str, role: FileRole) -> ParsedFile:
    """Read and parse a single markdown file, computing token statistics."""
    raw = _read_text(path)
    frontmatter, fm_raw, body, valid, error = split_frontmatter(raw)

    parsed = ParsedFile(
        path=path,
        relative_path=relative_path,
        role=role,
        raw_text=raw,
        frontmatter=frontmatter,
        body=body,
        frontmatter_valid=valid,
        frontmatter_error=error,
    )
    parsed.total_tokens = count_tokens(raw)
    parsed.frontmatter_tokens = count_tokens(fm_raw)
    parsed.body_tokens = count_tokens(body)

    description = parsed.description
    if description is not None:
        parsed.description_tokens = count_tokens(description)

    return parsed
