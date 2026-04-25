from __future__ import annotations

from pathlib import Path

from promptc.models import (
    INSUFFICIENT_MIN_BODY_TOKENS,
    INSUFFICIENT_MIN_SKILLS,
    FileRole,
    ParsedFile,
    ScanResult,
)


def _skill(rel: str, body_tokens: int) -> ParsedFile:
    return ParsedFile(
        path=Path("/fake") / rel,
        relative_path=rel,
        role=FileRole.SKILL,
        raw_text="",
        body="",
        body_tokens=body_tokens,
        total_tokens=body_tokens,
    )


def test_insufficient_when_too_few_skills(tmp_path: Path) -> None:
    # One huge skill: trips the file-count condition (< 3) regardless of body size.
    sr = ScanResult(root=tmp_path, files=[_skill("skills/big.md", 5000)])
    assert sr.is_insufficient is True


def test_insufficient_when_skills_below_body_threshold(tmp_path: Path) -> None:
    # Five tiny skills: passes file-count but trips body-token condition.
    files = [_skill(f"skills/s{i}.md", 50) for i in range(5)]
    sr = ScanResult(root=tmp_path, files=files)
    assert sr.skill_body_tokens == 250
    assert sr.skill_body_tokens < INSUFFICIENT_MIN_BODY_TOKENS
    assert sr.is_insufficient is True


def test_sufficient_when_both_conditions_pass(tmp_path: Path) -> None:
    files = [_skill(f"skills/s{i}.md", 500) for i in range(3)]
    sr = ScanResult(root=tmp_path, files=files)
    assert sr.skill_body_tokens == 1500
    assert sr.is_insufficient is False


def test_or_threshold_catches_placeholder_failure_mode(tmp_path: Path) -> None:
    """3 placeholder skills @ 50 tokens each — leaks through AND but trips OR.

    This is the explicit failure mode Persona A retest #3 surfaced: under the
    initially-proposed AND threshold, three near-empty SKILL.md files would
    pass Insufficient and get a trivial A+. OR fixes it.
    """
    files = [_skill(f"skills/placeholder_{i}.md", 50) for i in range(INSUFFICIENT_MIN_SKILLS)]
    sr = ScanResult(root=tmp_path, files=files)
    assert len(files) == INSUFFICIENT_MIN_SKILLS  # passes file-count condition
    assert sr.skill_body_tokens < INSUFFICIENT_MIN_BODY_TOKENS  # but trips body-tokens
    assert sr.is_insufficient is True  # OR catches it


def test_skill_body_tokens_excludes_non_skill_files(tmp_path: Path) -> None:
    skill = _skill("skills/x.md", 1000)
    other = ParsedFile(
        path=Path("/fake/CLAUDE.md"),
        relative_path="CLAUDE.md",
        role=FileRole.INSTRUCTIONS,
        raw_text="",
        body="",
        body_tokens=10000,  # huge instructions file
        total_tokens=10000,
    )
    sr = ScanResult(root=tmp_path, files=[skill, other])
    # Only skill body counts toward the threshold check.
    assert sr.skill_body_tokens == 1000
