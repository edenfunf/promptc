# Bloated `.claude/` demo fixture

> **This is a synthetic demo, not a real `.claude/`.** It is seeded with
> intentional duplication across skills so promptc has something dramatic
> to grade. Use this directory to reproduce the screenshots in the README.

## What's in here

Six SKILL.md files representing a hypothetical small-project setup:

- `security/SKILL.md` — generic security guidance
- `sql-safety/SKILL.md` — database-specific rules
- `python-style/SKILL.md` — Python-specific style + a few security mentions
- `code-review/SKILL.md` — review checklist that re-states many of the
  same rules
- `testing/SKILL.md` — test guidance with overlapping security points
- `legacy-rules/SKILL.md` — older guidance the team forgot to clean up;
  intentionally has **no `description` field** in its frontmatter so the
  fixture also exercises promptc's missing-description detection

Several rules ("always use parameterized queries", "validate input at the
boundary", "never log secrets", etc.) appear verbatim or near-verbatim
across multiple files. That's the failure mode promptc is built to find:
the engineer who maintains the .claude/ never noticed the same advice
got pasted into five different skill files.

## Reproduce

```bash
promptc analyze examples/bloated-demo
```

The grade should land in the D/F band, with the duplicate rules card
showing the cross-skill repetition.

## Why synthetic, not a real repo

Anthropic's own `anthropics/skills` repo grades A- — too clean to make a
dramatic demo. Rather than cherry-pick a community repo whose maintainer
hasn't agreed to be a public example, this fixture is built locally and
clearly labeled as such. Treat the numbers it produces as illustrative,
not benchmark-grade.
