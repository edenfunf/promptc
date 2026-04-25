# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-26

Initial public release.

### Added

- `promptc analyze [PATH]` — single-command audit of `.claude/`
  directories. Walks the tree, classifies files by role, and produces
  a self-contained HTML report alongside terminal output.
- Three-state report dispatch:
  - **Insufficient** when the scan has fewer than 3 SKILL.md files
    OR fewer than 1,000 aggregate body tokens (avoids misleading
    A+ on tiny setups).
  - **Clean (A–C)** with grade letter, headline, and a pointer to
    the Skill Context Exposure breakdown.
  - **Debt (D–F)** with the duplicate token count, bloat ratio,
    and the worst-case exposure multiplier in the hero.
- SaaS-style HTML dashboard:
  - Light theme, single blue accent, no glow / gradient fills.
  - 3-KPI strip (Duplicate Issues / High Risk Files / Total Tokens)
    replaces the older 5-card row.
  - 70/30 main split: bare tables on the left, severity-stripe alert
    panel + finding/action insights on the right.
  - Three accordions: Skill Context Exposure detail, all duplicate
    groups, and the methodology.
- Skill Context Exposure analysis:
  - Per-skill multiplier (`body / description`, content-only on
    both sides — frontmatter overhead excluded for symmetry).
  - Aggregate worst-case load and promised load.
  - Citations to the Anthropic Skills documentation and to the
    community-reported loading issue (`claude-code#14882`).
- Duplicate detection:
  - Word-set Jaccard similarity over paragraph chunks (default
    threshold 0.85, configurable).
  - Cross-language SDK path detector — duplicate clusters whose
    paths only differ in known language segments (e.g. `/python/`
    vs `/go/`) are surfaced for visibility but excluded from the
    bloat ratio.
- Token counting via OpenAI's `cl100k_base` as a Claude tokenizer
  proxy. Sampled against Claude on the anthropics/skills corpus
  (n=20, mixed prose+code via OpenRouter / Claude Sonnet 4.5);
  measured ~18% systematic underestimate (range −25% to −8%, stdev
  4.7pp, 20/20 files biased low). Disclaimer reflects the
  measurement so users can read absolute counts as lower bounds.
- Methodology section in the HTML report with formulas, threshold
  table, heuristic caveats, and the tokenizer disclaimer.
- JSON output (`--format json`) for CI / pipeline integration.
- CLI flags: `--threshold`, `--min-words`, `--exclude PATTERN`,
  `--output PATH`, `--no-html`, `--open`, `--verbose`.
- `scripts/validate_tokenizer.py` for users to recalibrate the
  tokenizer bias against their own corpus, with dual provider
  support (Anthropic native `count_tokens` or OpenRouter via
  `max_tokens=1` + `usage.prompt_tokens`) selected by env var.
- Cross-platform: tested on Windows / macOS / Linux × Python
  3.10 – 3.13 in CI.
- Examples: `examples/bloated-demo/.claude/` ships with the
  package as a representative D-grade fixture for documentation
  and test purposes.

### Notes

- **Bloat ratio, exposure multiplier, and Grade are unaffected by
  the ~18% tokenizer bias.** Numerator and denominator share the
  tokenizer, so the bias cancels in any ratio. Only absolute token
  counts shipped in reports are biased low; treat them as lower
  bounds.
- promptc runs fully locally. No data leaves the machine. No API
  keys are required to use the analyzer (`scripts/validate_tokenizer.py`
  is the only thing that hits a network API, and it is not invoked
  at runtime).
