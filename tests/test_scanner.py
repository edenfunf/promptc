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
