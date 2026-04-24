from __future__ import annotations

from promptc.tokens import DEFAULT_ENCODING, TOKENIZER_DISCLAIMER, count_tokens


def test_empty_string_is_zero_tokens() -> None:
    assert count_tokens("") == 0


def test_short_ascii_roundtrip() -> None:
    tokens = count_tokens("Hello, world!")
    assert tokens > 0
    assert tokens < 10


def test_longer_text_has_more_tokens() -> None:
    short = count_tokens("Use type hints.")
    longer = count_tokens("Use type hints. " * 20)
    assert longer > short


def test_chinese_text_tokenizes() -> None:
    tokens = count_tokens("請使用型別註記")
    assert tokens > 0


def test_special_tokens_are_not_disallowed() -> None:
    text = "This text mentions <|endoftext|> in passing."
    assert count_tokens(text) > 0


def test_disclaimer_mentions_approximation() -> None:
    assert "approximation" in TOKENIZER_DISCLAIMER.lower()
    assert "cl100k_base" in TOKENIZER_DISCLAIMER


def test_default_encoding_constant() -> None:
    assert DEFAULT_ENCODING == "cl100k_base"
