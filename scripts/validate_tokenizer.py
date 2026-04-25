#!/usr/bin/env python3
"""Compare tiktoken cl100k_base token counts against Claude's tokenizer.

Why: promptc reports token counts using tiktoken's cl100k_base as a proxy
for Claude's (non-public) tokenizer. The initial v0.1 calibration ran
this script against the anthropics/skills corpus (n=20, mixed prose+code
via OpenRouter / Claude Sonnet 4.5) and found cl100k_base underestimates
Claude tokens by ~18% (range -25% to -8%). That measurement now ships in
``TOKENIZER_DISCLAIMER``.

Re-run this script to:
  - Calibrate against a different corpus (CJK, pure code, etc.)
  - Re-validate after Claude tokenizer changes
  - Reproduce / contest the published number

Two provider paths, picked by env var:

    Anthropic native (preferred — count_tokens is free, no inference run):
        pip install anthropic
        export ANTHROPIC_API_KEY=sk-ant-...
        python scripts/validate_tokenizer.py path/to/skills/

    OpenRouter (fallback if Anthropic billing is blocked):
        pip install openai
        export OPENROUTER_API_KEY=sk-or-v1-...
        python scripts/validate_tokenizer.py path/to/skills/

OpenRouter does not expose count_tokens; this script sends a max_tokens=1
completion and reads usage.prompt_tokens. That costs ~1 token per file
(pennies for a 20-file run). Wrapper overhead may bias counts by 1-3
tokens per call which is well below noise for the variance question
this script tries to answer.

This script is never invoked by promptc at runtime; promptc itself
remains fully local.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from collections.abc import Callable
from pathlib import Path

from promptc.tokens import count_tokens as count_tiktoken

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4.5"


def _build_counter() -> tuple[Callable[[str], int], str]:
    """Pick provider via env var; return (count_fn, label).

    Anthropic native is preferred (free count_tokens). OpenRouter falls
    back to indirect count via usage.prompt_tokens on a max_tokens=1
    completion when Anthropic billing isn't accessible.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from anthropic import Anthropic
        except ImportError:
            print(
                "ANTHROPIC_API_KEY set but `anthropic` SDK missing.\n"
                "    pip install anthropic",
                file=sys.stderr,
            )
            sys.exit(1)
        client = Anthropic()
        model = os.environ.get("PROMPTC_VALIDATE_MODEL", DEFAULT_ANTHROPIC_MODEL)

        def count_anthropic(text: str) -> int:
            if not text.strip():
                return 0
            resp = client.messages.count_tokens(
                model=model,
                messages=[{"role": "user", "content": text}],
            )
            return resp.input_tokens

        return count_anthropic, f"anthropic native (count_tokens, model={model})"

    if os.environ.get("OPENROUTER_API_KEY"):
        try:
            from openai import OpenAI
        except ImportError:
            print(
                "OPENROUTER_API_KEY set but `openai` SDK missing.\n"
                "    pip install openai",
                file=sys.stderr,
            )
            sys.exit(1)
        client = OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        )
        model = os.environ.get("PROMPTC_VALIDATE_MODEL", DEFAULT_OPENROUTER_MODEL)

        def count_openrouter(text: str) -> int:
            if not text.strip():
                return 0
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": text}],
                max_tokens=1,
            )
            return resp.usage.prompt_tokens

        return count_openrouter, f"openrouter (max_tokens=1 + usage, model={model})"

    print(
        "Set ANTHROPIC_API_KEY or OPENROUTER_API_KEY before running.",
        file=sys.stderr,
    )
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "path",
        type=Path,
        help="Directory to scan for .md files (recursive).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum files to compare (default: 20). Saves API calls.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.path.is_dir():
        print(f"Not a directory: {args.path}", file=sys.stderr)
        return 1

    files = sorted(args.path.rglob("*.md"))
    if not files:
        print(f"No .md files found under {args.path}", file=sys.stderr)
        return 1

    files = files[: args.limit]
    counter, provider_label = _build_counter()

    print(f"Provider: {provider_label}")
    print(f"Comparing {len(files)} file(s).\n")
    print(f"{'File':<60s}  {'tiktoken':>9s}  {'claude':>9s}  {'delta':>6s}  {'pct':>7s}")
    print("-" * 100)

    deltas: list[float] = []
    total_tiktoken = 0
    total_claude = 0

    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  skip {fp.name}: {exc}", file=sys.stderr)
            continue

        tk = count_tiktoken(text)
        try:
            cl = counter(text)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {fp.name}: API error {exc}", file=sys.stderr)
            continue

        if cl == 0:
            continue

        pct = (tk - cl) / cl * 100.0
        deltas.append(pct)
        total_tiktoken += tk
        total_claude += cl

        display = str(fp.relative_to(args.path))
        if len(display) > 58:
            display = "..." + display[-55:]
        print(f"{display:<60s}  {tk:>9,d}  {cl:>9,d}  {tk - cl:>+6,d}  {pct:>+6.1f}%")

    if not deltas:
        print("\nNo files successfully compared.", file=sys.stderr)
        return 1

    print("-" * 100)
    print(f"{'AGGREGATE':<60s}  {total_tiktoken:>9,d}  {total_claude:>9,d}  "
          f"{total_tiktoken - total_claude:>+6,d}  "
          f"{(total_tiktoken - total_claude) / total_claude * 100:>+6.1f}%")

    print("\nDistribution of per-file percentage differences (tiktoken vs claude):")
    print(f"  count   : {len(deltas)}")
    print(f"  min     : {min(deltas):+.1f}%")
    print(f"  max     : {max(deltas):+.1f}%")
    print(f"  median  : {statistics.median(deltas):+.1f}%")
    print(f"  mean    : {statistics.mean(deltas):+.1f}%")
    if len(deltas) >= 2:
        print(f"  stdev   : {statistics.stdev(deltas):.1f}pp")

    max_abs = max(abs(d) for d in deltas)
    print(
        f"\nWorst-case absolute error across this sample: {max_abs:.1f}%.\n"
        "Interpretation:\n"
        "  - If max_abs < ~15% across a diverse sample, it is probably safe\n"
        "    to publish a concrete bound (e.g. 'typically within +/- 15%').\n"
        "  - If max_abs is larger or highly dependent on content type,\n"
        "    stick with the generic 'variance depends on content' disclaimer\n"
        "    that ships in TOKENIZER_DISCLAIMER."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
