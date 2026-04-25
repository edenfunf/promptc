---
name: python-style
description: Python code style, typing, and project conventions.
---

# Python Style

## Type hints

Use type hints in all function signatures, including return types.
Prefer concrete types over Any; reach for Protocol when you really need
duck typing. Run mypy or pyright in CI.

## Dataclasses and Pydantic

Use dataclasses for simple data containers; reach for Pydantic when you
need runtime validation at a system boundary. Do not use Pydantic
internally where dataclasses suffice — the validation cost is real.

## Imports

Sort imports with isort/ruff. One module per import line. Group:
stdlib, third-party, first-party, separated by blank lines.

## SQL safety

Always use parameterized queries for every database access. Never
concatenate user-provided strings into SQL statements directly. This
includes dynamic WHERE clauses, ORDER BY clauses, and table names.

## Logging

Never log secrets, personally identifiable information, or full request
or response bodies. Scrub sensitive fields at the logging boundary
using a structured logger.

## Boundary discipline

Treat any data that crossed a network or process boundary as untrusted
until proven otherwise. Apply the same scrutiny to data from other
internal services as you would to data from the public internet. The
threat model assumes lateral movement; act accordingly across every
service-to-service hop in the system.
