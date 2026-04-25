"""Token counting via tiktoken.

Claude's tokenizer is not publicly available. This module uses OpenAI's
`cl100k_base` as an approximation.

A sampled comparison against Claude (anthropics/skills, n=20, mixed
prose+code via OpenRouter) shows cl100k_base systematically
**underestimates** Claude tokens by ~18% (range -25% to -8%). The bias
is consistent in direction so:

  - Bloat ratio, exposure multiplier, and Grade are unaffected (numerator
    and denominator share the tokenizer; the bias cancels in any ratio).
  - Absolute counts shipped in reports are biased low; treat them as
    **lower bounds** for the true Claude cost.

CJK, pure-code, and non-English corpora are unmeasured. Run
`scripts/validate_tokenizer.py` to recalibrate against your own corpus.

Reports must surface ``TOKENIZER_DISCLAIMER`` so users see this caveat.
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken

DEFAULT_ENCODING = "cl100k_base"

TOKENIZER_DISCLAIMER = (
    "Token counts are approximations based on OpenAI's cl100k_base tokenizer. "
    "Claude's actual tokenizer is not publicly available. Sampled against "
    "Claude on the anthropics/skills corpus, cl100k_base systematically "
    "underestimates Claude tokens by ~18% (range -25% to -8%, n=20, mixed "
    "prose/code). Treat reported counts as lower bounds; actual Claude "
    "tokens are likely 15-25% higher on similar content."
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
