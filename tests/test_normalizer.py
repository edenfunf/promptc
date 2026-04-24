from __future__ import annotations

from promptc.normalizer import chunk_paragraphs, normalize


def test_lowercases() -> None:
    assert normalize("Hello World") == "hello world"


def test_collapses_whitespace() -> None:
    assert normalize("hello\n\n\t  world") == "hello world"


def test_strips_headers() -> None:
    assert normalize("# Title\n## Subtitle\nbody") == "title subtitle body"


def test_strips_list_bullets() -> None:
    assert normalize("- one\n- two\n* three\n+ four") == "one two three four"


def test_strips_blockquote() -> None:
    assert normalize("> quoted line") == "quoted line"


def test_strips_bold_and_italic() -> None:
    assert normalize("**bold** and *italic* and __also__ and _em_") == (
        "bold and italic and also and em"
    )


def test_keeps_link_text_drops_url() -> None:
    assert normalize("see [the docs](https://example.com)") == "see the docs"


def test_keeps_image_alt() -> None:
    assert normalize("![a cat](cat.png)") == "a cat"


def test_strips_inline_code_backticks_but_keeps_content() -> None:
    assert normalize("use `parameterized` queries") == "use parameterized queries"


def test_strips_trailing_punctuation() -> None:
    assert normalize("queries.") == "queries"
    assert normalize("don't stop") == "don t stop"


def test_strips_fenced_code_block() -> None:
    text = "prefix\n```python\nprint('hi')\n```\nsuffix"
    assert normalize(text) == "prefix suffix"


def test_strips_html_tags() -> None:
    assert normalize("<div>hello <b>world</b></div>") == "hello world"


def test_empty_string_is_empty() -> None:
    assert normalize("") == ""
    assert normalize("   \n\t ") == ""


def test_two_files_same_rule_normalize_equal() -> None:
    a = "**Always** use `parameterized` queries."
    b = "- Always use parameterized queries"
    assert normalize(a) == normalize(b)


def test_chunk_paragraphs_splits_on_blank_lines() -> None:
    body = "para one\nstill one\n\npara two\n\n\npara three"
    assert chunk_paragraphs(body) == ["para one\nstill one", "para two", "para three"]


def test_chunk_paragraphs_handles_empty() -> None:
    assert chunk_paragraphs("") == []
    assert chunk_paragraphs("   \n\n  ") == []


def test_chunk_paragraphs_strips_surrounding_whitespace() -> None:
    body = "\n\n  a paragraph  \n\n"
    assert chunk_paragraphs(body) == ["a paragraph"]
