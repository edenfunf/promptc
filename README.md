# promptc

> Measure worst-case context exposure in your Claude / Cursor setup.

**Status:** v0.1.0 in development. Not yet published to PyPI.

`promptc analyze` scans a `.claude/` directory and reports:

- **Context Debt** — absolute tokens wasted on duplicates and low-value content
- **Bloat Ratio** — what fraction of your context is waste
- **Efficiency Grade** — A / B / C / D / F, like SSL Labs
- **Progressive Disclosure Exposure** — worst-case load vs promised load

All analysis runs locally. No data leaves your machine. No API keys required.

## Install

```bash
pip install -e .          # while developing
```

## Usage

```bash
promptc analyze .claude/
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT
