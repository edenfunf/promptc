---
name: security
description: Project-wide security rules for handling untrusted input, secrets, and database access.
---

# Security

## SQL injection prevention

Always use parameterized queries for every database access. Never
concatenate user-provided strings into SQL statements directly. This
includes dynamic WHERE clauses, ORDER BY clauses, and table names.

## Input validation

Validate and sanitize all user-provided data at the system boundary
before it enters business logic. Reject inputs that do not match the
expected shape, range, or type. Prefer allowlists over denylists for
structured validation rules wherever possible.

## Secrets handling

Secrets must never be committed to the repository under any circumstance.
Use environment variables, a secrets manager, or a vault. Rotate any
leaked credentials immediately and audit access logs after any disclosure
event.

## Logging

Never log secrets, personally identifiable information, or full request
or response bodies. Scrub sensitive fields at the logging boundary using
a structured logger. Use structured logging consistently across all
services.

## Authentication

Use well-audited authentication libraries; do not roll your own crypto.
Rotate signing keys on a regular schedule. Expire idle sessions after a
reasonable inactivity timeout.

## Boundary discipline

Treat any data that crossed a network or process boundary as untrusted
until proven otherwise. Apply the same scrutiny to data from other
internal services as you would to data from the public internet. The
threat model assumes lateral movement; act accordingly across every
service-to-service hop in the system.
