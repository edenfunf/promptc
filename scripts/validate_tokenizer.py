#!/usr/bin/env python3
"""Compare tiktoken cl100k_base token counts against Anthropic's count_tokens API.

Why: promptc reports token counts using tiktoken's cl100k_base as a proxy
for Claude's (non-public) tokenizer. This script measures the actual error
margin against Anthropic's /v1/messages/count_tokens endpoint so we can
either (a) publish a concrete "typically within +/- X%" statement or
(b) stick with the generic "variance depends on content" disclaimer if
the error is unstable.

Usage:
    pip install anthropic        # not a runtime dep of promptc
    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/validate_tokenizer.py path/to/skills/

The script scans all `*.md` files under the given path, counts tokens
with both methods, and prints a per-file + aggregate comparison.

This script hits a network API and costs nothing (count_tokens is free),
but requires a key. It is not invoked by promptc at runtime; promptc
itself remains fully local.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print(
        "This script requires the anthropic SDK. Install with:\n"
        "    pip install anthropic",
        file=sys.stderr,
    )
    sys.exit(1)

from promptc.tokens import count_tokens as count_tiktoken

COUNT_MODEL = "claude-sonnet-4-5"


def count_anthropic(client: Anthropic, text: str) -> int:
    """Count tokens via Anthropic's public count_tokens endpoint."""
    if not text.strip():
        return 0
    response = client.messages.count_tokens(
        model=COUNT_MODEL,
        messages=[{"role": "user", "content": text}],
    )
    return response.input_tokens


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
    parser.add_argument(
        "--model",
        default=COUNT_MODEL,
        help=f"Anthropic model for count_tokens (default: {COUNT_MODEL}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY before running this script.", file=sys.stderr)
        return 1

    if not args.path.is_dir():
        print(f"Not a directory: {args.path}", file=sys.stderr)
        return 1

    files = sorted(args.path.rglob("*.md"))
    if not files:
        print(f"No .md files found under {args.path}", file=sys.stderr)
        return 1

    files = files[: args.limit]
    client = Anthropic()

    print(f"Comparing {len(files)} file(s) against {args.model}.\n")
    print(f"{'File':<60s}  {'tiktoken':>9s}  {'anthropic':>9s}  {'delta':>6s}  {'pct':>7s}")
    print("-" * 100)

    deltas: list[float] = []
    total_tiktoken = 0
    total_anthropic = 0

    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  skip {fp.name}: {exc}", file=sys.stderr)
            continue

        tk = count_tiktoken(text)
        try:
            an = count_anthropic(client, text)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {fp.name}: API error {exc}", file=sys.stderr)
            continue

        if an == 0:
            continue

        pct = (tk - an) / an * 100.0
        deltas.append(pct)
        total_tiktoken += tk
        total_anthropic += an

        display = str(fp.relative_to(args.path))
        if len(display) > 58:
            display = "..." + display[-55:]
        print(f"{display:<60s}  {tk:>9,d}  {an:>9,d}  {tk - an:>+6,d}  {pct:>+6.1f}%")

    if not deltas:
        print("\nNo files successfully compared.", file=sys.stderr)
        return 1

    print("-" * 100)
    print(f"{'AGGREGATE':<60s}  {total_tiktoken:>9,d}  {total_anthropic:>9,d}  "
          f"{total_tiktoken - total_anthropic:>+6,d}  "
          f"{(total_tiktoken - total_anthropic) / total_anthropic * 100:>+6.1f}%")

    print("\nDistribution of per-file percentage differences (tiktoken vs anthropic):")
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
