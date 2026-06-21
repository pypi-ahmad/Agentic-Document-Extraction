# ADR 0001 — Record architecture decisions

## Status

Accepted (2026-06-22).

## Context

The v0.3.0 modernization touched almost every layer of the
codebase. Future contributors (including future-us) need a place
to read the **why** behind the choices that are not obvious from
the code itself.

## Decision

We use ADRs to record every significant architectural decision. The
format is the one Michael Nygard described in 2011: a short
markdown file per decision, named ``NNNN-short-slug.md``, stored
in this directory, with a `Status` header (`Accepted`,
`Superseded`, or `Deprecated`).

## Consequences

- New ADRs are added to the bottom of this directory with the next
  free number.
- Superseded decisions are kept (renamed `NNNN-slug.md` →
  `NNNN-slug-superseded-by-NNNN.md`) and never deleted.
- The README in this directory points to the current set.
