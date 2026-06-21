# ADR 0003 — SQLite + WAL as the default persistence layer

## Status

Accepted (2026-06-22).

## Context

The project is local-first. The trade-off between SQLite and
PostgreSQL is real, but for a single-host, single-user service
SQLite is the better default.

## Decision

SQLite with WAL journaling is the default. PostgreSQL is a
documented swap (the same ORM models work; the connection string
changes).

## Rationale

- **Zero infrastructure.** No DB to install, no credentials to
  manage, no replica to maintain. `extraction.db` is one file you
  can back up with `cp`.
- **Crash safety with WAL.** WAL journaling gives the same
  per-statement durability as a network DB while still serving
  concurrent readers.
- **One-file deploy.** The Docker image persists the database
  file directly; no volume mount gymnastics.
- **Locality.** The SSE poller and the background pipeline both
  read and write the database; the latency difference between
  SQLite and Postgres over a UNIX socket is negligible at our
  scale.

## Consequences

- The application is single-writer by definition. A
  multi-replica deployment that uses SQLite needs a shared
  filesystem (NFS, EFS) or a swap to PostgreSQL.
- The job queue is local-first by default. The Arq/Redis backend
  in `app/services/jobs.py` is opt-in via `REDIS_URL`; this is
  the path to multi-worker horizontal scale.
- We will introduce a `DATABASE_URL=postgresql+asyncpg://…` mode
  in v0.4.0 once Alembic migrations have been validated against
  Postgres in CI.
