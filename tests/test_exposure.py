from __future__ import annotations

from pathlib import Path

from promptc.exposure import (
    ANTHROPIC_DOCS_URL,
    COMMUNITY_ISSUE_URL,
    EXPOSURE_NARRATIVE,
    analyze_exposure,
)
from promptc.models import FileRole, ParsedFile
from promptc.parser import parse_file


def _make(tmp_path: Path, name: str, text: str, role: FileRole) -> ParsedFile:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return parse_file(path, name, role)


def test_empty_input_produces_empty_report() -> None:
    report = analyze_exposure([])
    assert report.skill_count == 0
    assert report.total_promised == 0
    assert report.total_worst_case == 0
    assert report.multiplier is None


def test_non_skill_files_are_excluded(tmp_path: Path) -> None:
    files = [
        _make(tmp_path, "CLAUDE.md", "# instructions body\n", FileRole.INSTRUCTIONS),
        _make(tmp_path, "commands/review.md", "# review\n", FileRole.PROMPT),
        _make(tmp_path, "agents/r.md", "# agent body\n", FileRole.AGENT),
    ]
    report = analyze_exposure(files)
    assert report.skill_count == 0


def test_skill_with_name_and_description_computes_promised(tmp_path: Path) -> None:
    text = (
        "---\n"
        "name: security\n"
        "description: Parameterize queries and never concatenate user input.\n"
        "---\n"
        "# Body\n\n"
        "Long prose explaining the rule in detail for many tokens.\n"
    )
    parsed = _make(tmp_path, "skills/security/SKILL.md", text, FileRole.SKILL)
    report = analyze_exposure([parsed])

    assert report.skill_count == 1
    f = report.files[0]
    assert f.promised_tokens > 0
    assert f.worst_case_tokens == parsed.total_tokens
    assert f.worst_case_tokens > f.promised_tokens
    assert f.multiplier is not None
    assert f.multiplier > 1.0


def test_skill_without_description_has_zero_promised(tmp_path: Path) -> None:
    text = "# Security\n\nSome body content here.\n"
    parsed = _make(tmp_path, "skills/security/SKILL.md", text, FileRole.SKILL)
    report = analyze_exposure([parsed])

    f = report.files[0]
    assert f.promised_tokens == 0
    assert f.multiplier is None
    assert "skills/security/SKILL.md" in report.skills_without_description


def test_aggregate_multiplier_averages_correctly(tmp_path: Path) -> None:
    skill_a = _make(
        tmp_path,
        "skills/a/SKILL.md",
        "---\nname: a\ndescription: Short.\n---\n# A\n\n"
        "alpha beta gamma delta epsilon zeta eta theta iota kappa\n",
        FileRole.SKILL,
    )
    skill_b = _make(
        tmp_path,
        "skills/b/SKILL.md",
        "---\nname: b\ndescription: Also short.\n---\n# B\n\n"
        "one two three four five six seven eight nine ten\n",
        FileRole.SKILL,
    )
    report = analyze_exposure([skill_a, skill_b])

    assert report.skill_count == 2
    assert report.total_promised > 0
    assert report.total_worst_case == skill_a.total_tokens + skill_b.total_tokens
    assert report.multiplier is not None
    assert report.multiplier == report.total_worst_case / report.total_promised


def test_top_by_worst_case_orders_descending(tmp_path: Path) -> None:
    def skill(name: str, extra_body: str) -> ParsedFile:
        text = (
            f"---\nname: {name}\ndescription: One line.\n---\n# Body\n\n{extra_body}\n"
        )
        return _make(tmp_path, f"skills/{name}/SKILL.md", text, FileRole.SKILL)

    small = skill("small", "short body")
    medium = skill("medium", "medium length body " * 20)
    large = skill("large", "very long body text " * 80)

    report = analyze_exposure([small, medium, large])
    top = report.top_by_worst_case(3)

    assert [f.name for f in top] == ["large", "medium", "small"]


def test_exposure_narrative_cites_both_sides() -> None:
    assert ANTHROPIC_DOCS_URL in EXPOSURE_NARRATIVE
    assert COMMUNITY_ISSUE_URL in EXPOSURE_NARRATIVE
    lowered = EXPOSURE_NARRATIVE.lower()
    assert "progressive disclosure" in lowered
    assert "makes no claim" in lowered or "no claim" in lowered


def test_multiplier_none_when_all_skills_lack_description(tmp_path: Path) -> None:
    skill = _make(
        tmp_path,
        "skills/x/SKILL.md",
        "# Body only, no frontmatter\n\nplenty of body content here to count.\n",
        FileRole.SKILL,
    )
    report = analyze_exposure([skill])
    assert report.total_promised == 0
    assert report.multiplier is None
    assert report.total_worst_case > 0
