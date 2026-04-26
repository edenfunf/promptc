---
name: legacy-rules
---

# Legacy rules

Older guidance the team accumulated before consolidating onto the
current toolchain. Some of these are still in force; some have been
superseded by newer skills but the file was never cleaned up.

## Linting

Run `pylint` before every commit; CI rejects PRs with new pylint
warnings. (This is partly stale — most teams have moved to `ruff`,
but a couple of services still run pylint locally because their
configurations were never migrated.)

## SQL access

Always use parameterized queries for every database access. Never
concatenate user-provided strings into SQL statements directly. This
includes dynamic WHERE clauses, ORDER BY clauses, and table names.

## Type hints

Type hints are now required across the codebase (see `python-style`).
This file predates that decision; treat the older "type hints are
optional" guidance some skills carry as superseded.

## Boundary discipline

Treat any data that crossed a network or process boundary as untrusted
until proven otherwise. Apply the same scrutiny to data from other
internal services as you would to data from the public internet.
