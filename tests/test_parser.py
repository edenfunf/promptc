from __future__ import annotations

from pathlib import Path

from promptc.models import FileRole
from promptc.parser import parse_file, split_frontmatter


def test_split_frontmatter_missing() -> None:
    fm, raw, body, valid, error = split_frontmatter("# no frontmatter here\n\ntext")
    assert fm == {}
    assert raw == ""
    assert body == "# no frontmatter here\n\ntext"
    assert valid is True
    assert error is None


def test_split_frontmatter_well_formed() -> None:
    text = "---\nname: foo\ndescription: bar\n---\n# body\n"
    fm, raw, body, valid, error = split_frontmatter(text)
    assert fm == {"name": "foo", "description": "bar"}
    assert raw.startswith("---") and raw.rstrip().endswith("---")
    assert body == "# body\n"
    assert valid is True
    assert error is None


def test_split_frontmatter_malformed_yaml() -> None:
    text = "---\nname: foo\n  bad: : :\n---\nbody\n"
    fm, _raw, body, valid, error = split_frontmatter(text)
    assert fm == {}
    assert valid is False
    assert error is not None
    assert body == "body\n"


def test_split_frontmatter_unterminated_returns_whole_as_body() -> None:
    text = "---\nname: foo\n"  # no closing delimiter
    fm, raw, body, valid, error = split_frontmatter(text)
    assert fm == {}
    assert raw == ""
    assert body == text
    assert valid is True
    assert error is None


def test_split_frontmatter_scalar_not_mapping() -> None:
    text = "---\njust a string\n---\nbody\n"
    fm, _raw, _body, valid, error = split_frontmatter(text)
    assert fm == {}
    assert valid is False
    assert error is not None


def test_parse_file_with_frontmatter(tmp_path: Path) -> None:
    text = (
        "---\nname: sql-safety\ndescription: Parameterize queries.\n"
        "---\n# SQL Safety\n\nBody text.\n"
    )
    path = tmp_path / "SKILL.md"
    path.write_text(text, encoding="utf-8")

    parsed = parse_file(path, "SKILL.md", FileRole.SKILL)

    assert parsed.frontmatter_valid
    assert parsed.name == "sql-safety"
    assert parsed.description == "Parameterize queries."
    assert parsed.total_tokens > 0
    assert parsed.frontmatter_tokens > 0
    assert parsed.body_tokens > 0
    assert parsed.description_tokens is not None
    assert parsed.description_tokens > 0
    # Description tokens are always less than frontmatter tokens (subset of frontmatter).
    assert parsed.description_tokens < parsed.frontmatter_tokens


def test_parse_file_without_frontmatter(tmp_path: Path) -> None:
    text = "# Just a body\n\nNo frontmatter here.\n"
    path = tmp_path / "CLAUDE.md"
    path.write_text(text, encoding="utf-8")

    parsed = parse_file(path, "CLAUDE.md", FileRole.INSTRUCTIONS)

    assert parsed.frontmatter == {}
    assert parsed.frontmatter_tokens == 0
    assert parsed.description_tokens is None
    assert parsed.body_tokens == parsed.total_tokens


def test_parse_file_handles_utf8_bom(tmp_path: Path) -> None:
    text = "---\nname: bom-test\n---\nBody.\n"
    path = tmp_path / "SKILL.md"
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))

    parsed = parse_file(path, "SKILL.md", FileRole.SKILL)

    assert parsed.frontmatter_valid
    assert parsed.name == "bom-test"
