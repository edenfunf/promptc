from __future__ import annotations

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


def test_analyze_on_empty_dir_does_not_crash(tmp_path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
