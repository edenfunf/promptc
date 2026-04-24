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
    claude = root / ".claude"
    (claude / "skills" / "security").mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("# instructions\n", encoding="utf-8")
    (claude / "skills" / "security" / "SKILL.md").write_text(
        "---\nname: security\ndescription: Be safe.\n---\n# Body\n",
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
    assert payload["total_files"] == 2
    assert payload["total_tokens"] > 0
    paths = {f["path"] for f in payload["files"]}
    assert paths == {"CLAUDE.md", "skills/security/SKILL.md"}


def _seed_duplicates_fixture(root: Path) -> None:
    """Fixture with a 3-way near-duplicate rule to exercise dedup rendering.

    Each variant adds at most one or two trailing qualifier words so the
    Jaccard similarity between pairs lands in ~0.85-0.95 (caught at the
    0.85 default threshold, missed at 0.99 strict).
    """
    claude = root / ".claude"
    base = (
        "Always use parameterized queries for every database access. "
        "Never concatenate user-provided strings into SQL statements directly"
    )
    rules = {
        "security": f"{base}.",
        "python-security": f"**{base}** everywhere.",
        "db-rules": f"{base} at all times.",
    }
    for name, rule in rules.items():
        skill_dir = claude / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Rule source.\n---\n# {name}\n\n{rule}\n",
            encoding="utf-8",
        )


def test_analyze_renders_hero_panel(tmp_path: Path) -> None:
    _seed_duplicates_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    assert "CONTEXT DEBT REPORT" in result.output
    assert "tokens wasted" in result.output
    assert "Grade:" in result.output


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
    assert "CONTEXT DEBT REPORT" in html


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
