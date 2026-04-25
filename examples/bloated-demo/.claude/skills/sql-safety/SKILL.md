---
name: sql-safety
description: Database safety rules for the data-access layer.
---

# SQL Safety

## Parameterized queries

Always use parameterized queries for every database access. Never
concatenate user-provided strings into SQL statements directly. This
includes dynamic WHERE clauses, ORDER BY clauses, and table names.

## Migration discipline

All schema migrations go through the migrations/ directory and run in
the deploy pipeline; never modify the production schema by hand. Each
migration is reversible — pair every up with a tested down.

## Connection pooling

Use connection pools sized to peak concurrent load divided by average
query latency. Never open and close a fresh connection per request in a
hot path; the handshake cost dominates everything else under load.

## Read replicas

Route read-only queries to read replicas. Writes always go to primary.
Track replication lag and surface it on dashboards.

## Input validation

Validate and sanitize all user-provided data at the system boundary
before it enters business logic. Reject inputs that do not match the
expected shape, range, or type.

## Boundary discipline

Treat any data that crossed a network or process boundary as untrusted
until proven otherwise. Apply the same scrutiny to data from other
internal services as you would to data from the public internet. The
threat model assumes lateral movement; act accordingly across every
service-to-service hop in the system.
