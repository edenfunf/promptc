from __future__ import annotations

from pathlib import Path

from promptc.dedup import find_duplicates, jaccard
from promptc.models import FileRole, ParsedFile
from promptc.parser import parse_file


def test_jaccard_empty_vs_empty_is_one() -> None:
    assert jaccard(frozenset(), frozenset()) == 1.0


def test_jaccard_empty_vs_nonempty_is_zero() -> None:
    assert jaccard(frozenset(), frozenset({"a"})) == 0.0
    assert jaccard(frozenset({"a"}), frozenset()) == 0.0


def test_jaccard_identical() -> None:
    a = frozenset({"use", "type", "hints"})
    assert jaccard(a, a) == 1.0


def test_jaccard_disjoint() -> None:
    assert jaccard(frozenset({"a", "b"}), frozenset({"c", "d"})) == 0.0


def test_jaccard_partial_overlap() -> None:
    a = frozenset({"a", "b", "c"})
    b = frozenset({"b", "c", "d"})
    # intersection = 2, union = 4
    assert jaccard(a, b) == 0.5


def _make_parsed(tmp_path: Path, name: str, body: str) -> ParsedFile:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return parse_file(path, name, FileRole.SKILL)


def test_find_duplicates_with_no_files() -> None:
    result = find_duplicates([])
    assert result.total_groups == 0
    assert result.total_wasted_tokens == 0


def test_find_duplicates_with_no_dupes(tmp_path: Path) -> None:
    files = [
        _make_parsed(
            tmp_path,
            "a.md",
            "Always use parameterized queries for database access.\n\n"
            "This prevents SQL injection attacks.\n",
        ),
        _make_parsed(
            tmp_path,
            "b.md",
            "Prefer composition over inheritance in most object-oriented designs.\n",
        ),
    ]
    result = find_duplicates(files)
    assert result.total_groups == 0


def test_find_duplicates_detects_exact_duplicate_across_files(tmp_path: Path) -> None:
    rule = (
        "Always use parameterized queries for all database access.\n"
        "Never concatenate user input into SQL strings directly."
    )
    files = [
        _make_parsed(tmp_path, "skills/security.md", rule),
        _make_parsed(tmp_path, "skills/python-security.md", rule),
    ]
    result = find_duplicates(files)

    assert result.total_groups == 1
    group = result.groups[0]
    assert group.size == 2
    assert group.is_exact
    assert group.wasted_tokens > 0
    assert len(group.files_involved) == 2


def test_find_duplicates_detects_near_duplicate_via_formatting(tmp_path: Path) -> None:
    a = "Always use parameterized queries for all database access everywhere."
    b = "**Always** use _parameterized_ queries for all database access everywhere."
    files = [
        _make_parsed(tmp_path, "a.md", a),
        _make_parsed(tmp_path, "b.md", b),
    ]
    result = find_duplicates(files)

    assert result.total_groups == 1
    group = result.groups[0]
    assert group.is_exact  # markdown stripping makes them identical after normalization


def test_find_duplicates_respects_threshold(tmp_path: Path) -> None:
    a = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    b = "alpha beta gamma delta epsilon zeta eta theta mu nu"
    # 8 shared / 12 union = 0.667 — below 0.85 default
    files = [
        _make_parsed(tmp_path, "a.md", a),
        _make_parsed(tmp_path, "b.md", b),
    ]
    assert find_duplicates(files, threshold=0.85).total_groups == 0
    assert find_duplicates(files, threshold=0.5).total_groups == 1


def test_find_duplicates_skips_short_chunks(tmp_path: Path) -> None:
    files = [
        _make_parsed(tmp_path, "a.md", "short note\n"),
        _make_parsed(tmp_path, "b.md", "short note\n"),
    ]
    result = find_duplicates(files, min_words=5)
    assert result.total_groups == 0


def test_find_duplicates_wasted_tokens_attribution(tmp_path: Path) -> None:
    rule_long = (
        "Always use parameterized queries to prevent injection attacks. "
        "Never concatenate user-provided strings into SQL statements directly."
    )
    rule_short = (
        "Always use parameterized queries. "
        "Never concatenate user-provided strings into SQL statements."
    )
    files = [
        _make_parsed(tmp_path, "long.md", rule_long),
        _make_parsed(tmp_path, "short.md", rule_short),
    ]
    result = find_duplicates(files, threshold=0.6)

    assert result.total_groups == 1
    group = result.groups[0]
    # Longer one should be canonical.
    assert group.canonical.file_path == "long.md"
    # Short file's tokens appear in per_file_wasted.
    assert "short.md" in result.per_file_wasted
    assert "long.md" not in result.per_file_wasted


def test_language_variant_cluster_excluded_from_bloat(tmp_path: Path) -> None:
    """Persona C HN attack #4 fix: SDK READMEs duplicated per language binding
    should NOT count as bloat — they're legitimate per-binding docs.
    """
    rule = (
        "To create a managed agent, instantiate the client and call "
        "agents.create with a config object containing your model and tools."
    )
    files = [
        _make_parsed(tmp_path, "skills/claude-api/python/managed-agents/README.md", rule),
        _make_parsed(tmp_path, "skills/claude-api/go/managed-agents/README.md", rule),
        _make_parsed(tmp_path, "skills/claude-api/ruby/managed-agents/README.md", rule),
        _make_parsed(tmp_path, "skills/claude-api/typescript/managed-agents/README.md", rule),
    ]
    result = find_duplicates(files)

    # The cluster IS detected ...
    assert result.total_groups == 1
    group = result.groups[0]
    assert group.size == 4
    # ... but flagged as a language variant ...
    assert group.is_language_variant is True
    # ... and excluded from bloat-attributable totals.
    assert result.total_wasted_tokens == 0
    assert result.per_file_wasted == {}
    # ... but its tokens are still surfaced separately.
    assert result.language_variant_tokens > 0
    assert len(result.language_variant_groups) == 1
    assert len(result.bloat_groups) == 0


def test_non_language_variant_cluster_still_counts_as_bloat(tmp_path: Path) -> None:
    """Same content across non-language paths is still bloat."""
    rule = (
        "Always validate user input at the system boundary before processing. "
        "Reject inputs that do not match the expected shape."
    )
    files = [
        _make_parsed(tmp_path, "skills/security/SKILL.md", rule),
        _make_parsed(tmp_path, "skills/api-design/SKILL.md", rule),
        _make_parsed(tmp_path, "skills/code-review/SKILL.md", rule),
    ]
    result = find_duplicates(files)
    assert result.total_groups == 1
    group = result.groups[0]
    assert group.is_language_variant is False
    assert result.total_wasted_tokens > 0
    assert result.language_variant_tokens == 0


def test_language_variant_requires_all_paths_to_match_after_strip(tmp_path: Path) -> None:
    """Mixed cluster (some language-tagged paths, some not) is NOT a variant."""
    rule = (
        "Always parameterize SQL queries to prevent injection attacks "
        "across all database access paths in the codebase."
    )
    files = [
        _make_parsed(tmp_path, "skills/sql/python/README.md", rule),
        _make_parsed(tmp_path, "skills/sql/go/README.md", rule),
        # This third one has a different non-language path — breaks the variant.
        _make_parsed(tmp_path, "skills/security/SKILL.md", rule),
    ]
    result = find_duplicates(files)
    assert result.total_groups == 1
    assert result.groups[0].is_language_variant is False
    assert result.total_wasted_tokens > 0


def test_strip_language_segments_helper() -> None:
    from promptc.dedup import _strip_language_segments

    assert _strip_language_segments("skills/api/python/README.md") == "skills/api/README.md"
    assert _strip_language_segments("skills/api/go/README.md") == "skills/api/README.md"
    # Non-language segments are untouched
    assert _strip_language_segments("skills/security/SKILL.md") == "skills/security/SKILL.md"
    # Multiple language segments all stripped
    assert _strip_language_segments("a/python/b/go/c.md") == "a/b/c.md"
    # Case-insensitive
    assert _strip_language_segments("skills/Python/README.md") == "skills/README.md"


def test_find_duplicates_three_way_cluster(tmp_path: Path) -> None:
    rule = (
        "Always validate and sanitize user input at the system boundary before "
        "passing it to downstream services or persisting it to storage."
    )
    files = [
        _make_parsed(tmp_path, "a.md", rule),
        _make_parsed(tmp_path, "b.md", rule),
        _make_parsed(tmp_path, "c.md", rule),
    ]
    result = find_duplicates(files)

    assert result.total_groups == 1
    group = result.groups[0]
    assert group.size == 3
    # Two of the three are waste.
    assert len(result.per_file_wasted) == 2
