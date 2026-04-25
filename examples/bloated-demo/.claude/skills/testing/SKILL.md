---
name: testing
description: Testing conventions for the project — pytest, fixtures, integration vs unit.
---

# Testing

## Naming

Tests describe the behavior, not the function. `test_user_can_log_in_with_valid_credentials`, not `test_login_function`.

## Levels

Prefer integration tests over mocks when the integration is cheap.
Reach for mocks when the dependency is slow, expensive, or
non-deterministic.

## Fixtures

Use pytest fixtures for shared setup. Keep fixtures small and
composable. Avoid fixture chains deeper than two levels.

## Database tests

Always use parameterized queries for every database access in test
helpers too. Never concatenate user-provided strings into SQL statements
directly. This includes dynamic WHERE clauses, ORDER BY clauses, and
table names.

## CI

Tests run on every PR. The deploy pipeline runs them again with
production-like config. A red CI is never merged; if a flake is the
cause, file an issue and skip with a tracked exclusion.

## Boundary discipline

Treat any data that crossed a network or process boundary as untrusted
until proven otherwise. Apply the same scrutiny to data from other
internal services as you would to data from the public internet. The
threat model assumes lateral movement; act accordingly across every
service-to-service hop in the system.
