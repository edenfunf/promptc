"""Render the promptc analysis as a self-contained HTML report.

Design constraints:
    - Single file output: all CSS inlined, no external fetches, no CDN.
    - Offline-safe: opening the report file on an air-gapped machine
      must render correctly.
    - Screenshot-friendly: the hero section is the first thing a reader
      sees and should be legible as a standalone image.
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
    is_language_variant: bool
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
                is_language_variant=group.is_language_variant,
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


@dataclass(frozen=True)
class StatusBadge:
    """Right-aligned header pill + hero headline summarising the run.

    Three text fields with distinct purposes:
      - ``label``: 1-word status pill (header) — "Healthy" / "Needs attention"
      - ``headline``: hero subtitle below the grade letter — full phrase
      - ``level``: drives color — "ok" / "warn" / "critical" / "neutral"
    """

    label: str
    headline: str
    level: str


def _status_badge(scan_result: ScanResult, grade: Grade) -> StatusBadge:
    """Map the run's overall posture to a status pill + hero headline."""
    if scan_result.is_insufficient:
        return StatusBadge(
            label="Insufficient data",
            headline="Not enough to grade",
            level="neutral",
        )
    if grade.letter == "A":
        return StatusBadge(
            label="Healthy",
            headline="Healthy project",
            level="ok",
        )
    if grade.letter == "B":
        return StatusBadge(
            label="Mostly clean",
            headline="Mostly clean",
            level="warn",
        )
    if grade.letter == "C":
        return StatusBadge(
            label="Needs review",
            headline="Needs review",
            level="warn",
        )
    return StatusBadge(
        label="Needs attention",
        headline="Significant context debt",
        level="critical",
    )


def _hero_summary(
    scan_result: ScanResult,
    dedup_result: DedupResult,
    grade: Grade,
) -> str:
    """One-line plain-English summary shown under the hero headline.

    Carries the load-bearing test phrases ("tokens of duplicate content"
    + "Top offenders below" for debt; "Skill Context Exposure" pointer
    for clean) but reads as a single line, not a paragraph.
    """
    if scan_result.is_insufficient:
        if scan_result.total_files == 0:
            return "No files scanned. Point promptc at a directory with .claude/."
        return "Add more skills to enable grading."

    if grade.letter in ("D", "F"):
        return (
            f"{dedup_result.total_wasted_tokens:,} tokens of duplicate content "
            "across "
            f"{len(dedup_result.per_file_wasted)} files. Top offenders below."
        )

    if grade.letter == "A" and dedup_result.total_groups == 0:
        return "No structural issues found. See Skill Context Exposure below."

    if grade.letter == "A":
        return (
            f"{dedup_result.total_groups} small duplicate groups detected. "
            "See Skill Context Exposure below."
        )

    # B / C
    return (
        f"{dedup_result.total_groups} duplicate groups found "
        f"({grade.bloat_ratio:.0%} of total). "
        "See Skill Context Exposure below."
    )


@dataclass(frozen=True)
class Kpi:
    """One column in the 3-KPI header strip.

    Three KPIs replace the previous 5-card row. Each must answer a
    decision question, not just expose a raw number.
    """

    label: str    # "Duplicate Issues"
    value: str    # "124"
    detail: str   # "Mostly variants" / ">40x exposure" / "across 86 files"


_HIGH_RISK_MULTIPLIER = 40.0


def _compute_kpis(
    scan_result: ScanResult,
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
) -> list[Kpi]:
    """Return exactly 3 KPIs sized for the hero strip.

    Empty list for the Insufficient state (KPI strip is hidden).
    """
    if scan_result.is_insufficient:
        return []

    # 1. Duplicate Issues — show count + the cross-language exclusion
    #    so reviewers immediately understand whether the count is real.
    lv_count = len(dedup_result.language_variant_groups)
    if dedup_result.total_groups == 0:
        dup_detail = "no duplicates found"
    elif lv_count and lv_count == dedup_result.total_groups:
        dup_detail = "all are SDK variants"
    elif lv_count:
        dup_detail = f"{lv_count} are SDK variants"
    else:
        dup_detail = "all count toward grade"

    # 2. High Risk Files — count of skills above the exposure threshold
    high_risk = [
        f for f in exposure_result.files
        if f.multiplier and f.multiplier >= _HIGH_RISK_MULTIPLIER
    ]
    if high_risk:
        risk_detail = f">{int(_HIGH_RISK_MULTIPLIER)}x exposure"
    elif exposure_result.files:
        risk_detail = f"all under {int(_HIGH_RISK_MULTIPLIER)}x"
    else:
        risk_detail = "n/a"

    # 3. Total Tokens — context size across the scan
    return [
        Kpi(
            label="Duplicate Issues",
            value=f"{dedup_result.total_groups:,}",
            detail=dup_detail,
        ),
        Kpi(
            label="High Risk Files",
            value=str(len(high_risk)),
            detail=risk_detail,
        ),
        Kpi(
            label="Total Tokens",
            value=f"{scan_result.total_tokens:,}",
            detail=f"across {scan_result.total_files} files",
        ),
    ]


@dataclass(frozen=True)
class Insight:
    """One row in the right-column Insights panel.

    Each insight is a *finding* paired with a recommended *action*:

        finding: "Top 3 skills account for 46% of body size"
        action:  "Consider splitting them"

    Renders as two lines, the action prefixed with an arrow. `level`
    drives the dot color: "ok" / "warn" / "critical" / "info".
    """

    level: str
    finding: str
    action: str


def _compute_insights(
    scan_result: ScanResult,
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
    grade: Grade,
) -> list[Insight]:
    """Derive 2-4 actionable observations for the right-column panel.

    Empty list for Insufficient state (right panel will be hidden).
    """
    if scan_result.is_insufficient:
        return []

    out: list[Insight] = []

    # Concentration: top 3 skills' share of total worst-case body load.
    files = exposure_result.files
    worst_total = exposure_result.total_worst_case
    if files and worst_total:
        top3 = sum(f.worst_case_tokens for f in files[:3])
        share = top3 / worst_total
        if len(files) >= 4 and share >= 0.40:
            out.append(
                Insight(
                    level="warn" if share >= 0.60 else "info",
                    finding=f"Top 3 skills account for {share:.0%} of body size",
                    action="Consider splitting them or trimming bodies",
                )
            )

    # Cross-language SDK exclusion is a positive signal (detector working).
    lv_count = len(dedup_result.language_variant_groups)
    if lv_count and dedup_result.total_groups:
        share = lv_count / dedup_result.total_groups
        if share >= 0.20:
            out.append(
                Insight(
                    level="ok",
                    finding=(
                        f"{lv_count} of {dedup_result.total_groups} duplicate "
                        "groups are SDK variants"
                    ),
                    action="Already excluded from grade — no action needed",
                )
            )

    # Skills without descriptions — these load full body regardless.
    no_desc = exposure_result.skills_without_description
    if no_desc:
        out.append(
            Insight(
                level="critical",
                finding=(
                    f"{len(no_desc)} skill(s) missing description field"
                ),
                action="Add a description so Claude can defer the body load",
            )
        )

    # Largest single duplicate group — savings opportunity.
    if dedup_result.groups:
        top_group = dedup_result.groups[0]
        if not top_group.is_language_variant and top_group.wasted_tokens >= 200:
            out.append(
                Insight(
                    level="warn",
                    finding=(
                        f"Top duplicate group: {top_group.wasted_tokens:,} "
                        f"tokens repeated across {top_group.size} files"
                    ),
                    action="Extract to a shared reference and link from each",
                )
            )

    # Clean state with no other signals — short positive reassurance.
    if not out and grade.letter == "A":
        out.append(
            Insight(
                level="ok",
                finding="No actionable risks detected",
                action="Re-run after adding skills to keep the grade honest",
            )
        )

    return out[:4]


@dataclass(frozen=True)
class TopRisk:
    """One row in the right-column Alert / Risk panel.

    Renders like a log entry: severity stripe on the left, label
    (English, not raw number), target file, single-line context.
    """

    severity: str    # "high" | "medium"  — drives the left stripe color
    label: str       # "High exposure" / "Critical duplication" — human phrasing
    target: str      # file path
    detail: str      # one-line context with units


def _top_risks(
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
) -> list[TopRisk]:
    """Pick up to 3 single-item risks for the right-column Alert panel."""
    risks: list[TopRisk] = []

    # Worst exposure multiplier — anything >= 50× is "high", 20-50× medium.
    if exposure_result.files:
        for skill in exposure_result.files[:3]:
            if not skill.multiplier:
                continue
            if skill.multiplier >= 50:
                severity, label = "high", "High exposure"
            elif skill.multiplier >= 20:
                severity, label = "medium", "Elevated exposure"
            else:
                continue
            risks.append(
                TopRisk(
                    severity=severity,
                    label=label,
                    target=skill.file_path,
                    detail=(
                        f"{skill.multiplier:.1f}x more body tokens "
                        f"({skill.worst_case_tokens:,}) than declared "
                        f"description ({skill.promised_tokens:,})"
                    ),
                )
            )
            if len(risks) >= 2:
                break

    # Worst non-variant duplicate group — savings opportunity.
    bloat_group = next(
        (g for g in dedup_result.groups if not g.is_language_variant),
        None,
    )
    if bloat_group and bloat_group.wasted_tokens >= 200:
        risks.append(
            TopRisk(
                severity="medium" if bloat_group.wasted_tokens < 500 else "high",
                label=(
                    "Critical duplication"
                    if bloat_group.is_exact else "Heavy duplication"
                ),
                target=bloat_group.canonical.file_path,
                detail=(
                    f"{bloat_group.wasted_tokens:,} tokens repeated across "
                    f"{bloat_group.size} files"
                ),
            )
        )

    return risks[:3]


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
    return template.render(
        version=__version__,
        scan=scan_result,
        dedup=dedup_result,
        exposure=exposure_result,
        grade=grade,
        hero_state=_hero_state(scan_result, grade),
        status=_status_badge(scan_result, grade),
        hero_summary=_hero_summary(scan_result, dedup_result, grade),
        kpis=_compute_kpis(scan_result, dedup_result, exposure_result),
        skill_count=skill_count,
        skills_with_description=skills_with_desc,
        top_files=_top_files(scan_result, dedup_result, 10),
        top_duplicates=_top_duplicate_groups(dedup_result, 5),
        top_risks=_top_risks(dedup_result, exposure_result),
        insights=_compute_insights(scan_result, dedup_result, exposure_result, grade),
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
