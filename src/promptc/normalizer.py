"""Normalize markdown text for string-level duplicate detection.

The goal is to strip *formatting* while preserving the *content words*, so
two chunks that say the same thing with different markdown decoration
compare as similar.

Scope of stripping (v0.1):
    - Fenced code blocks (removed entirely; code dedup is out of scope)
    - Inline code backticks (backticks removed, content kept — e.g. ``parameterized``
      should still match a plain occurrence of "parameterized")
    - Image / link markdown (alt text and link text are kept)
    - HTML tags
    - Header markers (# ## ###)
    - Emphasis markers (** __ * _)
    - List bullet markers (- * +) at line starts
    - Blockquote markers (>) at line starts
    - Case (lowercased)
    - Punctuation (replaced with whitespace so "queries." and "queries" match)
    - Whitespace (collapsed to single spaces)
"""

from __future__ import annotations

import re

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]*)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HTML_TAG = re.compile(r"<[^>]+>")
_HEADER = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*\*|__)(.+?)\1|(?<!\w)([*_])(.+?)\3(?!\w)")
_LIST_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^\s*>\s+", re.MULTILINE)
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Return a canonicalized form of `text` suitable for similarity comparison."""
    text = _CODE_FENCE.sub(" ", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _HTML_TAG.sub(" ", text)
    text = _HEADER.sub("", text)
    text = _EMPHASIS.sub(lambda m: m.group(2) or m.group(4) or "", text)
    text = _LIST_BULLET.sub("", text)
    text = _BLOCKQUOTE.sub("", text)
    text = text.lower()
    text = _NON_WORD.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


def chunk_paragraphs(body: str) -> list[str]:
    """Split a markdown body into paragraph-sized chunks on blank lines."""
    if not body.strip():
        return []
    parts = re.split(r"\n\s*\n", body)
    return [p.strip() for p in parts if p.strip()]
