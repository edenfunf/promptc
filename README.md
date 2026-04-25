# promptc

> Measure worst-case skill-context exposure in your Claude Code setup.

**Status:** v0.1.0 in development. Not yet published to PyPI; install from source.

`promptc analyze` scans a `.claude/` directory and reports:

- **Skill Context Exposure** — worst-case (full SKILL.md body) vs promised
  (description-only) tokens, per skill and aggregate
- **Duplicate content** — paragraph-level near-duplicate detection across skills
- **Efficiency Grade** — A through F based on the duplicate-content ratio
  (see methodology below)

All analysis runs locally. No data leaves your machine. No API keys required.

## Install

```bash
pip install -e .          # from a local clone, while developing
```

## Usage

```bash
promptc analyze .          # scans ./.claude/ if present, else .
promptc analyze .claude/
promptc analyze . --no-html --format json
```

Run `promptc analyze --help` for all flags.

## Roadmap

- **v0.1.x** — Cross-language SDK path detector (down-weights duplicate
  clusters whose paths only differ in `/python/`, `/go/`, etc.); `--output`
  flag; tokenizer error magnitude published from sample runs.
- **v0.2** — `.cursor/rules/*.mdc` scanning. Today promptc only walks
  `.claude/`; if `.cursor/` is present as a sibling, the CLI surfaces a
  warning so the gap is explicit. Cursor support is tracked as a
  v0.2 milestone.
- **v0.2** — Methodology calibration: replace heuristic A/B/C/D/F
  thresholds with a reference distribution from real `.claude/`
  directories.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT
