from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from promptc import __version__
from promptc.cli import main


def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.output


def test_analyze_on_empty_dir_does_not_crash(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0


def _seed_fixture(root: Path) -> None:
    """Seed a non-insufficient fixture: ≥3 skills, ≥1k body tokens.

    Most CLI tests want to exercise the normal rendering path (hero, file
    table, exposure section, etc.). The Insufficient threshold is exercised
    by its own dedicated tests below.
    """
    claude = root / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("# instructions\n", encoding="utf-8")
    # Per-skill UNIQUE body to avoid 100%-duplicate F-grade artefact;
    # 100x repeats gives ≥1k aggregate body tokens to clear Insufficient.
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


def test_analyze_terminal_output_mentions_disclaimer(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    assert "cl100k_base" in result.output
    assert "security" in result.output


def test_analyze_json_output_is_valid(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path), "--format", "json"])
    assert result.exit_code == 0

    payload = json.loads(result.output)
    assert payload["total_files"] == 4  # CLAUDE.md + 3 skills
    assert payload["total_tokens"] > 0
    paths = {f["path"] for f in payload["files"]}
    assert paths == {
        "CLAUDE.md",
        "skills/security/SKILL.md",
        "skills/testing/SKILL.md",
        "skills/logging/SKILL.md",
    }


def _seed_duplicates_fixture(root: Path) -> None:
    """Fixture with a 3-way near-duplicate rule + filler to clear Insufficient.

    Each variant adds at most one or two trailing qualifier words so the
    Jaccard similarity between pairs lands in ~0.85-0.95 (caught at the
    0.85 default threshold, missed at 0.99 strict). Each file also gets
    enough non-duplicate filler text to push aggregate body tokens past the
    Insufficient threshold (≥1k).
    """
    claude = root / ".claude"
    base = (
        "Always use parameterized queries for every database access. "
        "Never concatenate user-provided strings into SQL statements directly"
    )
    # Non-duplicate filler text per file so dedup ratio is meaningful AND
    # we clear the Insufficient body-token threshold.
    filler_phrases = {
        "security": "Validate all input at boundaries and reject malformed data. ",
        "python-security": "Prefer the standard library's secrets module for token gen. ",
        "db-rules": "Use connection pools sized to peak load divided by query latency. ",
    }
    rules = {
        "security": f"{base}.",
        "python-security": f"**{base}** everywhere.",
        "db-rules": f"{base} at all times.",
    }
    for name, rule in rules.items():
        skill_dir = claude / "skills" / name
        skill_dir.mkdir(parents=True)
        filler = filler_phrases[name] * 60  # ~ 400-500 tokens of unique content
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Rule source.\n---\n# {name}\n\n"
            f"{rule}\n\n{filler}\n",
            encoding="utf-8",
        )


def test_analyze_renders_hero_panel(tmp_path: Path) -> None:
    _seed_duplicates_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    # New 3-state hero: at minimum, the grade letter and a forward-pointer
    # line ("See ... below") must appear when the fixture is sufficient.
    grades = ("A+", "A-", "B+", "B-", "C+", "C-", "D+", "D-", "F")
    assert any(letter in result.output for letter in grades)
    # Pointer line in clean hero, or full section heading in debt state.
    assert "Skill Context Exposure" in result.output


def test_analyze_renders_savings_when_duplicates_exist(tmp_path: Path) -> None:
    _seed_duplicates_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    assert "Estimated Savings" in result.output
    assert "Post-dedup" in result.output


def test_analyze_hides_savings_when_no_duplicates(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    assert "Estimated Savings" not in result.output


def test_analyze_renders_exposure_section(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    assert "Skill Context Exposure" in result.output
    assert "Exposure multiplier" in result.output


def test_threshold_flag_suppresses_near_duplicates(tmp_path: Path) -> None:
    _seed_duplicates_fixture(tmp_path)
    runner = CliRunner()
    # A threshold of 0.99 should disqualify the near-duplicates in the
    # fixture (they differ slightly in wording).
    strict = runner.invoke(
        main, ["analyze", str(tmp_path), "--threshold", "0.99", "--format", "json"]
    )
    default = runner.invoke(main, ["analyze", str(tmp_path), "--format", "json"])
    assert strict.exit_code == 0 and default.exit_code == 0

    strict_groups = json.loads(strict.output)["duplicates"]["total_groups"]
    default_groups = json.loads(default.output)["duplicates"]["total_groups"]
    assert default_groups >= 1
    assert strict_groups < default_groups


def test_min_words_flag_suppresses_short_chunks(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir()
    # Two files with the same short-but-identical chunk; at min-words=5 the
    # chunk should survive the filter and be flagged.
    for name in ("a", "b"):
        (claude / f"{name}.md").write_text(
            "Use the parameterized queries always.\n", encoding="utf-8"
        )
    runner = CliRunner()

    default = runner.invoke(main, ["analyze", str(tmp_path), "--format", "json"])
    aggressive = runner.invoke(
        main, ["analyze", str(tmp_path), "--min-words", "10", "--format", "json"]
    )
    assert default.exit_code == 0 and aggressive.exit_code == 0

    default_groups = json.loads(default.output)["duplicates"]["total_groups"]
    aggressive_groups = json.loads(aggressive.output)["duplicates"]["total_groups"]
    assert default_groups >= 1
    assert aggressive_groups == 0


def test_exclude_flag_filters_by_basename(tmp_path: Path) -> None:
    _seed_duplicates_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "analyze",
            str(tmp_path),
            "--exclude",
            "skills/security/*",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    paths = {f["path"] for f in json.loads(result.output)["files"]}
    assert not any(p.startswith("skills/security/") for p in paths)


def test_exclude_flag_supports_multiple_patterns(tmp_path: Path) -> None:
    _seed_duplicates_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "analyze",
            str(tmp_path),
            "--exclude",
            "skills/security/*",
            "--exclude",
            "skills/db-rules/*",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    paths = {f["path"] for f in json.loads(result.output)["files"]}
    assert paths == {"skills/python-security/SKILL.md"}


def test_json_output_contains_grade_block(tmp_path: Path) -> None:
    _seed_duplicates_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path), "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    grade = payload["grade"]
    assert set(grade) == {"letter", "modifier", "display", "bloat_ratio"}
    assert grade["letter"] in {"A", "B", "C", "D", "F"}
    assert 0.0 <= grade["bloat_ratio"] <= 1.0


def test_empty_dir_skips_hero_and_exposure(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    assert "CONTEXT DEBT REPORT" not in result.output
    assert "Skill Context Exposure" not in result.output
    assert "No markdown files" in result.output


def test_analyze_writes_html_report_to_cwd_by_default(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0

    report = Path("promptc-report.html").resolve()
    assert report.exists(), "analyze should write promptc-report.html to cwd"
    assert "Full report:" in result.output
    html = report.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    # New 3-state hero: at minimum the hero panel must be present.
    assert "<section class=\"hero" in html


def test_no_html_flag_skips_report_file(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path), "--no-html"])
    assert result.exit_code == 0
    assert not Path("promptc-report.html").exists()
    assert "Full report:" not in result.output


def test_no_html_with_open_warns(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path), "--no-html", "--open"])
    assert result.exit_code == 0
    assert "--open has no effect" in result.output
    assert not Path("promptc-report.html").exists()


def test_json_format_does_not_write_html(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path), "--format", "json"])
    assert result.exit_code == 0
    assert not Path("promptc-report.html").exists()


def test_output_flag_writes_report_to_chosen_path(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    target = tmp_path / "custom-name.html"
    runner = CliRunner()
    result = runner.invoke(
        main, ["analyze", str(tmp_path), "--output", str(target)]
    )
    assert result.exit_code == 0
    assert target.exists()
    # Default filename should NOT also be written.
    assert not Path("promptc-report.html").exists()


def test_empty_dir_default_points_at_written_html(tmp_path: Path) -> None:
    """When the scanned dir has no .md files, default flow still writes the
    Insufficient-state HTML report — terminal output should hint at it
    instead of contradicting itself with 'No files found' + silent file-write."""
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    assert "No markdown files found" in result.output
    assert "empty-state report has still been written" in result.output
    assert Path("promptc-report.html").exists()


def test_empty_dir_no_html_explains_what_promptc_looks_for(tmp_path: Path) -> None:
    """With --no-html, no report is written — terminal hint should describe
    what promptc scans for instead of pointing at a non-existent file."""
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path), "--no-html"])
    assert result.exit_code == 0
    assert "No markdown files found" in result.output
    assert ".claude/skills/" in result.output
    assert "empty-state report has still been written" not in result.output
    assert not Path("promptc-report.html").exists()


def test_output_with_no_html_warns(tmp_path: Path) -> None:
    _seed_fixture(tmp_path)
    target = tmp_path / "should-not-exist.html"
    runner = CliRunner()
    result = runner.invoke(
        main, ["analyze", str(tmp_path), "--no-html", "--output", str(target)]
    )
    assert result.exit_code == 0
    assert not target.exists()
    assert "--output has no effect" in result.output
