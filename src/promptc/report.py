"""Render the promptc analysis as a self-contained HTML report.

Design constraints:
    - Single file output: all CSS inlined, no external fetches, no CDN.
    - Offline-safe: opening the report file on an air-gapped machine
      must render correctly.
    - Screenshot-friendly: the hero section is the first thing a reader
      sees and should be legible as a standalone image.

Day 8 scope: Hero section + Top 10 largest files. Day 9 extends with
duplicates detail and the skill context exposure block.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jinja2

from promptc import __version__
from promptc.dedup import DedupResult
from promptc.exposure import (
    ANTHROPIC_DOCS_URL,
    COMMUNITY_ISSUE_URL,
    EXPOSURE_NARRATIVE,
    ExposureReport,
)
from promptc.grade import Grade
from promptc.models import ScanResult
from promptc.tokens import TOKENIZER_DISCLAIMER

TEMPLATE_DIR = Path(__file__).parent / "templates"
DEFAULT_REPORT_FILENAME = "promptc-report.html"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
    autoescape=jinja2.select_autoescape(["html", "j2"]),
    undefined=jinja2.StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _load_styles() -> str:
    """Read the bundled CSS file. Inlined into the report for offline use."""
    return (TEMPLATE_DIR / "report.css").read_text(encoding="utf-8")


@dataclass(frozen=True)
class TopFileRow:
    rank: int
    path: str
    role: str
    total_tokens: int
    duplicate_tokens: int
    duplicate_ratio: float


@dataclass(frozen=True)
class DuplicateChunkCard:
    file_path: str
    chunk_index: int
    tokens: int
    is_canonical: bool
    preview: str


@dataclass(frozen=True)
class DuplicateGroupCard:
    rank: int
    kind: str
    size: int
    wasted_tokens: int
    canonical_file: str
    chunks: list[DuplicateChunkCard]


# Common Unicode punctuation → ASCII fallback so previews render without
# mojibake on legacy Windows consoles (cp950 / cp1252) and look identical
# in plain-ASCII contexts. Run before truncation.
_ASCII_FALLBACKS = {
    "—": "--",   # em dash
    "–": "-",    # en dash
    "…": "...",  # ellipsis
    "“": '"',    # left double quote
    "”": '"',    # right double quote
    "‘": "'",    # left single quote
    "’": "'",    # right single quote
    "•": "*",    # bullet
    " ": " ",    # non-breaking space
}


def _ascii_safe(text: str) -> str:
    """Replace common smart-punctuation with ASCII equivalents."""
    for src, dst in _ASCII_FALLBACKS.items():
        text = text.replace(src, dst)
    return text


def _chunk_preview(text: str, max_chars: int = 280) -> str:
    """Collapse whitespace; ASCII-fold smart punctuation; truncate at word boundary."""
    collapsed = _ascii_safe(" ".join(text.split()))
    if len(collapsed) <= max_chars:
        return collapsed
    cut = collapsed[: max_chars - 1].rsplit(" ", 1)[0]
    return cut + " ..."


def _top_duplicate_groups(
    dedup_result: DedupResult, limit: int = 5
) -> list[DuplicateGroupCard]:
    """Top N groups by wasted tokens, with canonical chunk listed first."""
    cards: list[DuplicateGroupCard] = []
    for rank, group in enumerate(dedup_result.groups[:limit], start=1):
        canonical = group.canonical
        ordered = [canonical] + [c for c in group.chunks if c is not canonical]
        cards.append(
            DuplicateGroupCard(
                rank=rank,
                kind="exact" if group.is_exact else "near",
                size=group.size,
                wasted_tokens=group.wasted_tokens,
                canonical_file=canonical.file_path,
                chunks=[
                    DuplicateChunkCard(
                        file_path=c.file_path,
                        chunk_index=c.chunk_index,
                        tokens=c.tokens,
                        is_canonical=(c is canonical),
                        preview=_chunk_preview(c.raw),
                    )
                    for c in ordered
                ],
            )
        )
    return cards


def _top_files(
    scan_result: ScanResult,
    dedup_result: DedupResult,
    limit: int = 10,
) -> list[TopFileRow]:
    """Return the N files with the largest total token cost, ranked desc."""
    ranked = sorted(
        scan_result.files,
        key=lambda f: f.total_tokens,
        reverse=True,
    )[:limit]

    rows: list[TopFileRow] = []
    for i, f in enumerate(ranked, start=1):
        dup_tokens = dedup_result.per_file_wasted.get(f.relative_path, 0)
        ratio = (dup_tokens / f.body_tokens) if f.body_tokens else 0.0
        rows.append(
            TopFileRow(
                rank=i,
                path=f.relative_path,
                role=f.role.value,
                total_tokens=f.total_tokens,
                duplicate_tokens=dup_tokens,
                duplicate_ratio=ratio,
            )
        )
    return rows


def _hero_state(scan_result: ScanResult, grade: Grade) -> str:
    """Return one of "insufficient", "debt", or "clean" for hero dispatch."""
    if scan_result.is_insufficient:
        return "insufficient"
    if grade.letter in ("D", "F"):
        return "debt"
    return "clean"


def render_html(
    scan_result: ScanResult,
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
    grade: Grade,
) -> str:
    """Render the analysis as a single self-contained HTML document."""
    template = _env.get_template("report.html.j2")
    skill_count = exposure_result.skill_count
    skills_with_desc = skill_count - len(exposure_result.skills_without_description)
    body_total = sum(f.body_tokens for f in scan_result.files)
    return template.render(
        version=__version__,
        scan=scan_result,
        dedup=dedup_result,
        exposure=exposure_result,
        grade=grade,
        hero_state=_hero_state(scan_result, grade),
        skill_count=skill_count,
        skills_with_description=skills_with_desc,
        body_total_tokens=body_total,
        top_files=_top_files(scan_result, dedup_result, 10),
        top_duplicates=_top_duplicate_groups(dedup_result, 5),
        disclaimer=TOKENIZER_DISCLAIMER,
        exposure_narrative=EXPOSURE_NARRATIVE,
        anthropic_docs_url=ANTHROPIC_DOCS_URL,
        community_issue_url=COMMUNITY_ISSUE_URL,
        styles=_load_styles(),
    )


def write_report(path: Path, html: str) -> Path:
    """Write the rendered HTML to `path` (UTF-8) and return the resolved path."""
    path.write_text(html, encoding="utf-8")
    return path.resolve()
