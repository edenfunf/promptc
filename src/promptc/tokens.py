"""Token counting via tiktoken.

Claude's tokenizer is not publicly available. This module uses OpenAI's
`cl100k_base` as an approximation. Actual variance depends on content type
(code-heavy, non-English, unusual Unicode). Reports must surface the
disclaimer text below so users understand the approximation.
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken

DEFAULT_ENCODING = "cl100k_base"

TOKENIZER_DISCLAIMER = (
    "Token counts are approximations based on OpenAI's cl100k_base tokenizer. "
    "Claude's actual tokenizer is not publicly available; variance depends on "
    "content type. Use these numbers as order-of-magnitude estimates."
)


@lru_cache(maxsize=4)
def _get_encoding(name: str = DEFAULT_ENCODING) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def count_tokens(text: str, encoding_name: str = DEFAULT_ENCODING) -> int:
    """Return the token count of `text` under the given encoding.

    Empty strings return 0 without invoking the tokenizer.
    """
    if not text:
        return 0
    enc = _get_encoding(encoding_name)
    return len(enc.encode(text, disallowed_special=()))
