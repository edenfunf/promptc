"""Shared pytest fixtures for the promptc test suite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test with cwd pointing at the per-test tmp_path.

    `promptc analyze` writes ``promptc-report.html`` to ``Path.cwd()`` by
    default. Without this fixture, CLI tests would spray those reports into
    the project root. Monkey-patching cwd to tmp_path isolates each test
    and keeps the repo clean.
    """
    monkeypatch.chdir(tmp_path)
    # Sanity: make sure nothing in the test suite accidentally relies on
    # the project root as cwd. `os.getcwd()` should match tmp_path now.
    assert Path(os.getcwd()).resolve() == tmp_path.resolve()
