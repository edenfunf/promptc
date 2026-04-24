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
