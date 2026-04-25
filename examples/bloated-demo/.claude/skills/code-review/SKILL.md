---
name: code-review
description: Pull request review checklist for the team.
---

# Code Review Checklist

Read the diff once for shape, then again for correctness. Comment on
intent, not just style.

## Security

Always use parameterized queries for every database access. Never
concatenate user-provided strings into SQL statements directly. This
includes dynamic WHERE clauses, ORDER BY clauses, and table names.

Validate and sanitize all user-provided data at the system boundary
before it enters business logic. Reject inputs that do not match the
expected shape, range, or type.

Secrets must never be committed to the repository under any
circumstance. If you see one in a diff, ask the author to revoke it
before merging.

## Tests

Every PR must add tests for new behavior. Tests should describe the
behavior, not the implementation. Prefer integration tests over mocks
when the integration is cheap.

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
