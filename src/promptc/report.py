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
from promptc.exposure import ExposureReport
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


def render_html(
    scan_result: ScanResult,
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
    grade: Grade,
) -> str:
    """Render the analysis as a single self-contained HTML document."""
    template = _env.get_template("report.html.j2")
    return template.render(
        version=__version__,
        scan=scan_result,
        dedup=dedup_result,
        exposure=exposure_result,
        grade=grade,
        top_files=_top_files(scan_result, dedup_result, 10),
        disclaimer=TOKENIZER_DISCLAIMER,
        styles=_load_styles(),
    )


def write_report(path: Path, html: str) -> Path:
    """Write the rendered HTML to `path` (UTF-8) and return the resolved path."""
    path.write_text(html, encoding="utf-8")
    return path.resolve()
