from __future__ import annotations

from pathlib import Path

from promptc.dedup import find_duplicates
from promptc.exposure import analyze_exposure
from promptc.grade import compute_grade
from promptc.report import _top_files, render_html, write_report
from promptc.scanner import scan


def _seed(root: Path) -> None:
    claude = root / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("# instructions\n", encoding="utf-8")
    skill_dir = claude / "skills" / "security"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: security\ndescription: Be safe.\n---\n"
        "# Security\n\nAlways use parameterized queries.\n",
        encoding="utf-8",
    )


def _analyze(tmp_path: Path):
    scan_result = scan(tmp_path)
    dedup_result = find_duplicates(scan_result.files)
    exposure_result = analyze_exposure(scan_result.files)
    total = scan_result.total_tokens
    ratio = dedup_result.total_wasted_tokens / total if total else 0.0
    grade = compute_grade(ratio)
    return scan_result, dedup_result, exposure_result, grade


def test_render_html_produces_non_empty_output(tmp_path: Path) -> None:
    _seed(tmp_path)
    html = render_html(*_analyze(tmp_path))
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_render_html_has_no_external_fetches(tmp_path: Path) -> None:
    """Report must be fully self-contained for offline / local-first use.

    Matches attribute patterns that would cause a browser to fetch a remote
    resource; explanatory mentions of the word "CDN" in CSS comments do not.
    """
    _seed(tmp_path)
    html = render_html(*_analyze(tmp_path))
    assert "<script src=" not in html
    assert '<link rel="stylesheet"' not in html
    assert "@import url(" not in html
    # No http(s) URLs in src/href attributes — file:// and relative refs ok.
    import re
    remote_refs = re.findall(r'(?:src|href)\s*=\s*["\']https?://', html)
    assert remote_refs == [], f"unexpected remote refs: {remote_refs}"


def test_render_html_includes_hero_content(tmp_path: Path) -> None:
    _seed(tmp_path)
    scan_r, dedup_r, exposure_r, grade = _analyze(tmp_path)
    html = render_html(scan_r, dedup_r, exposure_r, grade)

    assert "CONTEXT DEBT REPORT" in html
    assert grade.display in html
    assert f"hero--{grade.letter.lower()}" in html
    assert "tokens wasted" in html


def test_render_html_includes_top_files_table(tmp_path: Path) -> None:
    _seed(tmp_path)
    scan_r, dedup_r, exposure_r, grade = _analyze(tmp_path)
    html = render_html(scan_r, dedup_r, exposure_r, grade)

    assert "Top" in html
    assert "largest files" in html
    assert "skills/security/SKILL.md" in html
    assert "CLAUDE.md" in html


def test_render_html_includes_version_and_disclaimer(tmp_path: Path) -> None:
    from promptc import __version__

    _seed(tmp_path)
    html = render_html(*_analyze(tmp_path))
    assert __version__ in html
    assert "cl100k_base" in html  # disclaimer


def test_render_html_escapes_html_in_file_paths(tmp_path: Path) -> None:
    """File paths are rendered via {{ f.path }} — Jinja2 autoescape should
    neutralise any HTML metacharacters that happen to appear in a filename
    on case-insensitive or unusual filesystems.

    We can't actually create a file with `<script>` in its name on Windows,
    so we render the template directly with an adversarial path to verify
    autoescape is wired up.
    """
    from promptc.dedup import DedupResult
    from promptc.exposure import ExposureReport
    from promptc.grade import compute_grade
    from promptc.models import FileRole, ScanResult
    from promptc.report import TopFileRow, _env

    template = _env.get_template("report.html.j2")
    scan_r = ScanResult(root=tmp_path)
    dedup_r = DedupResult()
    exposure_r = ExposureReport()
    grade = compute_grade(0.0)
    top = [
        TopFileRow(
            rank=1,
            path="<script>alert(1)</script>.md",
            role=FileRole.SKILL.value,
            total_tokens=100,
            duplicate_tokens=0,
            duplicate_ratio=0.0,
        )
    ]
    html = template.render(
        version="test",
        scan=scan_r,
        dedup=dedup_r,
        exposure=exposure_r,
        grade=grade,
        top_files=top,
        disclaimer="",
        styles="",
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_top_files_ranks_by_total_tokens(tmp_path: Path) -> None:
    claude = tmp_path / ".claude" / "skills"
    claude.mkdir(parents=True)
    (claude / "small.md").write_text("---\nname: small\n---\n# A\nshort\n", encoding="utf-8")
    (claude / "big.md").write_text(
        "---\nname: big\n---\n# B\n" + ("padding words " * 80) + "\n",
        encoding="utf-8",
    )
    scan_r = scan(tmp_path)
    dedup_r = find_duplicates(scan_r.files)
    rows = _top_files(scan_r, dedup_r, limit=10)

    assert rows[0].path == "skills/big.md"
    assert rows[0].total_tokens > rows[-1].total_tokens
    # Rank is 1-indexed and sequential.
    assert [r.rank for r in rows] == list(range(1, len(rows) + 1))


def test_top_files_respects_limit(tmp_path: Path) -> None:
    claude = tmp_path / ".claude" / "skills"
    claude.mkdir(parents=True)
    for i in range(15):
        (claude / f"skill_{i:02d}.md").write_text(
            f"---\nname: s{i}\n---\n# B {i}\n{'text ' * (i + 5)}\n",
            encoding="utf-8",
        )
    scan_r = scan(tmp_path)
    dedup_r = find_duplicates(scan_r.files)
    rows = _top_files(scan_r, dedup_r, limit=5)
    assert len(rows) == 5


def test_write_report_creates_file(tmp_path: Path) -> None:
    _seed(tmp_path)
    html = render_html(*_analyze(tmp_path))
    out = tmp_path / "report.html"
    result = write_report(out, html)
    assert result.exists()
    assert result.read_text(encoding="utf-8") == html


def test_render_html_with_empty_scan_still_renders(tmp_path: Path) -> None:
    # Directory exists but no markdown files.
    html = render_html(*_analyze(tmp_path))
    assert "<!DOCTYPE html>" in html
    assert "No files scanned." in html
