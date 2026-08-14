# ADR 0002 — Bounded page processing

## Status

Superseded by the stateless V2 runtime (2026-08-14).

## Decision

The active request path uses direct Python orchestration for document pages and bounded
model verification. Legacy graph-based modules may remain for compatibility, but the
FastAPI application does not create a durable graph runtime.

This keeps the observable workflow explicit: validate, render, draft, ground, verify, and
assemble one response.
