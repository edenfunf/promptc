from __future__ import annotations

from pathlib import Path

from promptc.models import FileRole
from promptc.scanner import classify, resolve_scan_root, scan


def test_classify_claude_md_at_root() -> None:
    assert classify(("CLAUDE.md",)) == FileRole.INSTRUCTIONS


def test_classify_agents_md_at_root() -> None:
    assert classify(("AGENTS.md",)) == FileRole.INSTRUCTIONS


def test_classify_skill_nested() -> None:
    assert classify(("skills", "security", "SKILL.md")) == FileRole.SKILL


def test_classify_skill_flat() -> None:
    assert classify(("skills", "security.md")) == FileRole.SKILL


def test_classify_skill_support_file_is_other() -> None:
    assert classify(("skills", "security", "reference.md")) == FileRole.OTHER
    assert classify(("skills", "claude-api", "examples", "streaming.md")) == FileRole.OTHER
    assert classify(("skills", "deep", "nested", "support", "file.md")) == FileRole.OTHER


def test_classify_skill_md_case_insensitive() -> None:
    assert classify(("skills", "security", "Skill.md")) == FileRole.SKILL


def test_classify_skill_md_at_root_when_scanned_inside_skills_tree() -> None:
    # Bug #11: pointing promptc at /tmp/anthropics-skills/skills/ produces
    # relative paths like ('pdf', 'SKILL.md') with no 'skills' segment.
    # SKILL.md must still be classified as SKILL.
    assert classify(("pdf", "SKILL.md")) == FileRole.SKILL
    assert classify(("SKILL.md",)) == FileRole.SKILL
    assert classify(("any", "deep", "nested", "SKILL.md")) == FileRole.SKILL


def test_classify_skill_md_takes_priority_over_other_path_signals() -> None:
    # Even if a SKILL.md happens to live under commands/ or agents/, it is
    # still a skill — filename wins over directory.
    assert classify(("commands", "SKILL.md")) == FileRole.SKILL
    assert classify(("agents", "SKILL.md")) == FileRole.SKILL


def test_classify_prompt() -> None:
    assert classify(("commands", "review.md")) == FileRole.PROMPT


def test_classify_agent() -> None:
    assert classify(("agents", "reviewer.md")) == FileRole.AGENT


def test_classify_other() -> None:
    assert classify(("README.md",)) == FileRole.OTHER
    assert classify(("docs", "notes.md")) == FileRole.OTHER


def test_classify_empty_tuple() -> None:
    assert classify(()) == FileRole.OTHER


def test_resolve_scan_root_prefers_dot_claude(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    assert resolve_scan_root(tmp_path) == tmp_path / ".claude"


def test_resolve_scan_root_falls_back(tmp_path: Path) -> None:
    assert resolve_scan_root(tmp_path) == tmp_path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scan_empty_dir(tmp_path: Path) -> None:
    result = scan(tmp_path)
    assert result.files == []
    assert result.warnings == []


def test_scan_nonexistent_path_reports_warning(tmp_path: Path) -> None:
    result = scan(tmp_path / "does-not-exist")
    assert result.files == []
    assert any("does not exist" in w for w in result.warnings)


def test_scan_discovers_and_classifies(tmp_path: Path) -> None:
    _write(tmp_path / "CLAUDE.md", "# instructions\n")
    _write(
        tmp_path / "skills" / "security" / "SKILL.md",
        "---\nname: security\ndescription: Be safe.\n---\n# Security\n",
    )
    _write(tmp_path / "commands" / "review.md", "# Review\n")
    _write(tmp_path / "agents" / "reviewer.md", "# Reviewer agent\n")
    _write(tmp_path / "notes" / "random.md", "# random\n")

    result = scan(tmp_path)
    roles = {f.relative_path: f.role for f in result.files}

    assert roles["CLAUDE.md"] == FileRole.INSTRUCTIONS
    assert roles["skills/security/SKILL.md"] == FileRole.SKILL
    assert roles["commands/review.md"] == FileRole.PROMPT
    assert roles["agents/reviewer.md"] == FileRole.AGENT
    assert roles["notes/random.md"] == FileRole.OTHER
    assert result.total_tokens > 0


def test_scan_skips_hidden_dirs(tmp_path: Path) -> None:
    _write(tmp_path / ".git" / "config.md", "# nope\n")
    _write(tmp_path / "node_modules" / "pkg.md", "# nope\n")
    _write(tmp_path / "CLAUDE.md", "# yes\n")

    result = scan(tmp_path)
    paths = {f.relative_path for f in result.files}

    assert paths == {"CLAUDE.md"}


def test_scan_reports_malformed_frontmatter(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "broken" / "SKILL.md",
        "---\nname: x\n  bad: : :\n---\nbody\n",
    )
    result = scan(tmp_path)
    assert len(result.files) == 1
    assert not result.files[0].frontmatter_valid
    assert any("SKILL.md" in w for w in result.warnings)


def test_scan_prefers_dot_claude_subdir(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "CLAUDE.md", "# inside\n")
    _write(tmp_path / "README.md", "# outside\n")

    result = scan(tmp_path)
    paths = {f.relative_path for f in result.files}

    assert paths == {"CLAUDE.md"}
    assert result.root == (tmp_path / ".claude").resolve()


def test_scan_detects_cursor_sibling_count(tmp_path: Path) -> None:
    """When `.cursor/rules/` is a sibling of `.claude/`, count its .mdc files."""
    _write(tmp_path / ".claude" / "skills" / "x" / "SKILL.md", "---\nname: x\n---\nbody\n")
    _write(tmp_path / ".cursor" / "rules" / "general.mdc", "rule body\n")
    _write(tmp_path / ".cursor" / "rules" / "tests.mdc", "rule body\n")
    _write(tmp_path / ".cursor" / "rules" / "nested" / "api.mdc", "rule body\n")

    result = scan(tmp_path)
    assert result.cursor_sibling_files == 3


def test_scan_no_cursor_sibling_returns_zero(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "skills" / "x" / "SKILL.md", "---\nname: x\n---\nbody\n")
    result = scan(tmp_path)
    assert result.cursor_sibling_files == 0


def test_scan_cursor_sibling_when_no_dot_claude(tmp_path: Path) -> None:
    """If user points at a dir without .claude/, still detect adjacent .cursor/."""
    _write(tmp_path / "skills" / "x" / "SKILL.md", "---\nname: x\n---\nbody\n")
    _write(tmp_path / ".cursor" / "rules" / "rule.mdc", "rule\n")
    result = scan(tmp_path)
    assert result.cursor_sibling_files == 1


def test_scan_exclude_matches_by_basename(tmp_path: Path) -> None:
    """Patterns without path separators should match by basename alone, even
    when the file lives deep in a tree."""
    _write(
        tmp_path / "skills" / "auth" / "SKILL.md",
        "---\nname: auth\ndescription: x\n---\nbody\n",
    )
    _write(tmp_path / "skills" / "auth" / "scratch.md", "scratch")
    result = scan(tmp_path, excludes=("scratch.md",))
    paths = {f.relative_path for f in result.files}
    assert "skills/auth/SKILL.md" in paths
    assert "skills/auth/scratch.md" not in paths


def test_scan_path_pointing_to_file_warns(tmp_path: Path) -> None:
    """If the resolved scan root is a file rather than a directory, surface
    that as a warning instead of crashing."""
    target = tmp_path / "single.md"
    target.write_text("hello", encoding="utf-8")
    result = scan(target)
    assert result.files == []
    assert any("not a directory" in w for w in result.warnings)


def test_scan_skips_dotfile_md(tmp_path: Path) -> None:
    """`.hidden.md` style files are skipped — they're typically editor
    swap files or backup junk, not user-authored content."""
    _write(
        tmp_path / "skills" / "auth" / "SKILL.md",
        "---\nname: auth\ndescription: x\n---\nbody\n",
    )
    _write(tmp_path / "skills" / "auth" / ".hidden.md", "stash")
    result = scan(tmp_path)
    paths = {f.relative_path for f in result.files}
    assert "skills/auth/SKILL.md" in paths
    assert all(not Path(p).name.startswith(".") for p in paths)


def test_scan_skips_non_markdown_files(tmp_path: Path) -> None:
    """Anything that isn't .md or .mdc is ignored."""
    _write(
        tmp_path / "skills" / "auth" / "SKILL.md",
        "---\nname: auth\ndescription: x\n---\nbody\n",
    )
    _write(tmp_path / "skills" / "auth" / "notes.txt", "notes")
    _write(tmp_path / "skills" / "auth" / "config.yaml", "k: v")
    result = scan(tmp_path)
    paths = {f.relative_path for f in result.files}
    assert paths == {"skills/auth/SKILL.md"}
