from __future__ import annotations

from pathlib import Path

from promptc.dedup import find_duplicates
from promptc.exposure import analyze_exposure
from promptc.grade import compute_grade
from promptc.report import _top_files, render_html, write_report
from promptc.scanner import scan


def _seed(root: Path) -> None:
    """Sufficient fixture with unique body content per skill (Grade A territory)."""
    claude = root / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("# instructions\n", encoding="utf-8")
    fillers = {
        "security": "Validate inputs at every boundary before processing them. ",
        "testing": "Prefer integration tests over mocks when the integration is cheap. ",
        "logging": "Use structured logging and scrub PII at the boundary always. ",
    }
    for name, filler in fillers.items():
        skill_dir = claude / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} guidance.\n---\n"
            f"# {name.title()}\n\n{filler * 100}\n",
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


def test_render_html_has_no_external_resource_fetches(tmp_path: Path) -> None:
    """Report must not auto-fetch remote resources on page load.

    `<a href>` citation links to the docs / community issue are allowed
    (user-clickable, no page-load fetch); but `<script src=>`, `<link
    rel=stylesheet href=>`, `<img src=>`, `<iframe src=>`, and `@import`
    would trigger auto-fetches and break offline viewing.
    """
    _seed(tmp_path)
    html = render_html(*_analyze(tmp_path))
    assert "<script src=" not in html
    assert '<link rel="stylesheet"' not in html
    assert "@import url(" not in html
    import re
    for tag in ("script", "link", "img", "iframe"):
        pattern = rf"<{tag}[^>]*\b(?:src|href)\s*=\s*[\"']https?://"
        assert re.search(pattern, html, re.IGNORECASE) is None, (
            f"{tag} tag would auto-fetch a remote resource"
        )


def test_render_html_includes_hero_content(tmp_path: Path) -> None:
    _seed(tmp_path)
    scan_r, dedup_r, exposure_r, grade = _analyze(tmp_path)
    html = render_html(scan_r, dedup_r, exposure_r, grade)

    # New 3-state hero: grade letter + grade-keyed CSS class are present.
    assert grade.display in html
    assert f"hero--{grade.letter.lower()}" in html
    # The "See Skill Context Exposure below" pointer fires on clean/moderate
    # states; debt state has "Top offenders below". One of these two strings
    # should be present for any sufficient fixture.
    assert "Skill Context Exposure" in html or "Top offenders below" in html


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
        hero_state="clean",
        skill_count=0,
        skills_with_description=0,
        body_total_tokens=0,
        top_files=top,
        top_duplicates=[],
        disclaimer="",
        exposure_narrative="",
        anthropic_docs_url="",
        community_issue_url="",
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


def _seed_with_duplicates(root: Path) -> None:
    """Three-way near-duplicate fixture, padded past the Insufficient threshold."""
    claude = root / ".claude" / "skills"
    claude.mkdir(parents=True)
    base = (
        "# Security\n\n"
        "Always use parameterized queries for every database access. "
        "Never concatenate user-provided strings into SQL statements directly."
    )
    # Per-file unique filler so the dedup signal is meaningful AND aggregate
    # body tokens clear the Insufficient ≥1k threshold.
    fillers = {
        "security": "Audit access logs after any disclosure event regularly. ",
        "python-security": "Prefer the standard library secrets module always. ",
        "db-rules": "Size connection pools to peak load divided by latency. ",
    }
    for name, body_extra in fillers.items():
        (claude / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: SQL safety rule.\n---\n\n"
            f"{base}\n\n{body_extra * 50}\n",
            encoding="utf-8",
        )


def test_render_html_renders_exposure_section(tmp_path: Path) -> None:
    _seed_with_duplicates(tmp_path)
    html = render_html(*_analyze(tmp_path))
    assert "Skill Context Exposure" in html
    assert "Promised load" in html
    assert "Worst-case load" in html
    assert "Exposure multiplier" in html
    # Narrative + citations (collapse whitespace so the phrase survives any
    # template line-wrapping).
    flat = " ".join(html.split()).lower()
    assert "code.claude.com" in flat
    assert "14882" in flat
    assert "makes no claim" in flat


def test_render_html_hides_exposure_when_no_skills(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "CLAUDE.md").write_text("# only instructions\n", encoding="utf-8")
    html = render_html(*_analyze(tmp_path))
    # The exposure CARD must not render; the term may still appear in the
    # methodology section (which always renders as informational reference).
    assert 'class="card exposure"' not in html
    assert "Worst-case load" not in html


def test_render_html_renders_duplicates_section(tmp_path: Path) -> None:
    _seed_with_duplicates(tmp_path)
    html = render_html(*_analyze(tmp_path))
    assert "Duplicate rules" in html
    # New (Day 13): non-variant clusters say "duplicate tokens" rather than
    # the editorial "tokens wasted".
    assert "duplicate tokens" in html
    # At least one chunk is tagged canonical
    assert "canonical" in html
    # All three source files appear in the duplicate comparison
    for name in ("security.md", "python-security.md", "db-rules.md"):
        assert f"skills/{name}" in html


def test_render_html_hides_duplicates_section_when_none(tmp_path: Path) -> None:
    claude = tmp_path / ".claude" / "skills"
    claude.mkdir(parents=True)
    (claude / "a.md").write_text(
        "---\nname: a\ndescription: Unique one.\n---\n# A\n\n"
        "Prefer composition over inheritance in object-oriented designs.\n",
        encoding="utf-8",
    )
    (claude / "b.md").write_text(
        "---\nname: b\ndescription: Unique two.\n---\n# B\n\n"
        "Always validate input at the system boundary before processing.\n",
        encoding="utf-8",
    )
    html = render_html(*_analyze(tmp_path))
    assert "Duplicate rules" not in html


def test_render_html_escapes_chunk_preview_text(tmp_path: Path) -> None:
    """Chunk previews come from file contents; autoescape must neutralise them."""
    claude = tmp_path / ".claude" / "skills"
    claude.mkdir(parents=True)
    payload = (
        "---\nname: xss\ndescription: html-escape on chunk text.\n---\n\n"
        "This chunk contains <script>alert('x')</script> and &amp; plus more "
        "words to clear the min-words filter for dedup tests.\n"
    )
    (claude / "a.md").write_text(payload, encoding="utf-8")
    (claude / "b.md").write_text(payload, encoding="utf-8")
    html = render_html(*_analyze(tmp_path))
    assert "<script>alert('x')</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_anthropic_docs_and_issue_urls_linked(tmp_path: Path) -> None:
    _seed_with_duplicates(tmp_path)
    html = render_html(*_analyze(tmp_path))
    # The URLs appear inside <a href="..."> elements, not just as text.
    assert 'href="https://code.claude.com/docs/en/skills"' in html
    assert (
        'href="https://github.com/anthropics/claude-code/issues/14882"' in html
    )


def test_chunk_preview_truncates_long_text() -> None:
    from promptc.report import _chunk_preview

    short = "short paragraph"
    assert _chunk_preview(short) == short

    long_text = "word " * 200
    out = _chunk_preview(long_text, max_chars=80)
    assert len(out) <= 80
    assert out.endswith(" ...")
    assert "word word" in out


def test_render_html_insufficient_state_renders_distinct_hero(tmp_path: Path) -> None:
    """Sub-threshold fixture should produce the Insufficient hero, not a grade hero."""
    claude = tmp_path / ".claude" / "skills" / "x"
    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text(
        "---\nname: x\ndescription: tiny.\n---\n# X\n\nshort body.\n",
        encoding="utf-8",
    )
    html = render_html(*_analyze(tmp_path))
    assert "NOT ENOUGH TO AUDIT YET" in html
    assert "hero--insufficient" in html
    # Per D-Δ1: insufficient copy must surface the Cursor v0.2 note.
    assert ".cursor/rules/" in html
    assert "v0.2" in html
    # Exposure CARD must not render in insufficient state (methodology section
    # may still mention "Skill Context Exposure" as a reference heading).
    assert 'class="card exposure"' not in html


def test_render_html_debt_state_shows_multiplier_in_hero(tmp_path: Path) -> None:
    """A D/F-grade fixture should put the multiplier IN the hero as supporting evidence."""
    claude = tmp_path / ".claude" / "skills"
    claude.mkdir(parents=True)
    # Heavy duplication + enough volume to clear Insufficient AND grade ≥ D
    rule = "Always parameterize SQL queries every single time without exception. " * 40
    for name in ("a", "b", "c", "d"):
        (claude / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: sql.\n---\n# {name}\n\n{rule}\n",
            encoding="utf-8",
        )
    scan_r, dedup_r, exposure_r, grade = _analyze(tmp_path)
    # Sanity: this fixture should actually be in debt-state territory
    assert grade.letter in ("D", "F"), f"fixture didn't grade D/F: got {grade.display}"
    html = render_html(scan_r, dedup_r, exposure_r, grade)
    assert "Top offenders below" in html
    assert "tokens of duplicate content" in html


def test_render_html_clean_state_hides_multiplier_from_hero(tmp_path: Path) -> None:
    """A-grade fixture should NOT show multiplier in hero, only via 'see below' pointer."""
    _seed(tmp_path)  # 3 unique skills, no duplicates, A+ grade
    scan_r, dedup_r, exposure_r, grade = _analyze(tmp_path)
    # Sanity check
    assert grade.letter == "A", f"_seed should grade A: got {grade.display}"
    html = render_html(scan_r, dedup_r, exposure_r, grade)
    # The hero block (between <section class="hero..."> and the next </section>)
    # should not contain "Exposure multiplier" — that lives in the dedicated card.
    import re
    hero_match = re.search(
        r'<section class="hero[^"]*">(.*?)</section>', html, re.DOTALL
    )
    assert hero_match, "hero section not found"
    hero_block = hero_match.group(1)
    assert "Exposure multiplier" not in hero_block
    # But it must point at the section below.
    assert "Skill Context Exposure" in hero_block


def test_render_html_surfaces_cursor_sibling_warning(tmp_path: Path) -> None:
    """When .cursor/rules/ is detected, hero must be preceded by a warning banner."""
    _seed(tmp_path)
    cursor_rules = tmp_path / ".cursor" / "rules"
    cursor_rules.mkdir(parents=True)
    (cursor_rules / "general.mdc").write_text("rule\n", encoding="utf-8")
    (cursor_rules / "tests.mdc").write_text("rule\n", encoding="utf-8")
    html = render_html(*_analyze(tmp_path))
    assert "cursor-warning" in html
    assert ".cursor/rules/" in html
    assert "2 file" in html  # count surfaced
    assert "v0.2" in html


def test_methodology_section_present_with_thresholds_and_caveats(tmp_path: Path) -> None:
    """Per Persona C re-test: methodology must ship at launch, not Day 12 deferred.

    Asserts that the report exposes the formulae, the threshold table, and
    honest 'heuristic' caveats — these together neutralise the rewritten
    HN comment about an undefended grade being elevated to entire product.
    """
    _seed(tmp_path)
    html = render_html(*_analyze(tmp_path))

    # Section header
    assert 'id="methodology"' in html
    assert "How this is graded" in html

    # Formulae expressed exactly
    assert "bloat_ratio = duplicate_tokens / total_tokens" in html
    assert "multiplier = SKILL.md body tokens / description tokens" in html

    # Threshold table includes all 5 letter grades and the percentage breakpoints
    for letter in ("A", "B", "C", "D", "F"):
        assert f"grade-pill--{letter.lower()}" in html
    for pct in ("5%", "15%", "25%", "40%"):
        assert pct in html

    # Honest caveats — the language Persona C said was missing
    flat = " ".join(html.split()).lower()
    assert "thresholds are heuristic" in flat
    assert "v0.2 will replace them" in flat
    assert "not empirically calibrated" in flat


def test_methodology_section_includes_tokenizer_disclaimer_and_cjk_caveat(tmp_path: Path) -> None:
    """Tokenizer disclaimer migrated INTO methodology, not buried in footer."""
    _seed(tmp_path)
    html = render_html(*_analyze(tmp_path))
    flat = " ".join(html.split()).lower()
    # Standard disclaimer appears under the Token counts heading
    assert "cl100k_base" in html
    # Plus the CJK / code error-magnitude expansion
    assert "cjk" in flat or "code-heavy" in flat
    assert "validate_tokenizer.py" in html


def test_hero_disclaimer_links_to_methodology(tmp_path: Path) -> None:
    """Per Persona C re-test: short disclaimer must stay adjacent to the hero
    so the caveat travels with the headline number; full caveats live in
    methodology and the hero links to it.
    """
    _seed(tmp_path)
    html = render_html(*_analyze(tmp_path))
    assert 'class="hero-disclaimer"' in html
    assert 'href="#methodology"' in html


def test_table_columns_have_descriptive_titles(tmp_path: Path) -> None:
    """Vocabulary subtitles via title= attributes for browser tooltips."""
    _seed(tmp_path)
    html = render_html(*_analyze(tmp_path))
    # Bloat column header gets a title attribute explaining the metric
    assert 'title="Share of this file' in html


def test_top_duplicate_groups_limits_and_orders(tmp_path: Path) -> None:
    from promptc.report import _top_duplicate_groups

    _seed_with_duplicates(tmp_path)
    _, dedup_r, _, _ = _analyze(tmp_path)
    cards = _top_duplicate_groups(dedup_r, limit=5)
    assert len(cards) == dedup_r.total_groups
    # Canonical is always the first chunk in the ordered list.
    for card in cards:
        assert card.chunks[0].is_canonical
        assert sum(1 for c in card.chunks if c.is_canonical) == 1
