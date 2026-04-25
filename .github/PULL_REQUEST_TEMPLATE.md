## What this PR does

<!-- One-paragraph summary in prose. -->

## Why

<!-- Link the issue this addresses, or describe the motivation. -->

Closes #

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Documentation only
- [ ] Tooling / CI

## How to verify

<!-- Concrete steps a reviewer can run locally. -->

```bash
pytest
ruff check .
promptc analyze examples/bloated-demo
```

## Checklist

- [ ] Tests added or updated for any user-facing behaviour change
- [ ] `pytest` passes locally
- [ ] `ruff check .` passes
- [ ] `README.md` / methodology copy updated if a metric definition
      or threshold changed
- [ ] No secrets, API keys, or local-machine paths committed
- [ ] If the change is sample-based (e.g. tokenizer recalibration),
      the sample size and source are documented in the disclaimer
