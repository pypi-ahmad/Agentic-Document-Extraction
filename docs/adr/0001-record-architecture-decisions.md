# ADR 0001: Record architecture decisions

## Status

Accepted (2026-06-22); reviewed for Paperplane 5.0.0 (2026-08-14).

## Context

Paperplane has changed from a multi-service application to a local Streamlit workspace.
This directory records why its architectural boundaries exist, including decisions that
can be hard to understand when older technologies still appear in Git history or archived plans.

## Decision

Record significant architectural choices as short Markdown ADRs in this directory. Each ADR
includes Context, Decision, Consequences, and one status: Proposed, Accepted, Deprecated, or
Superseded. Give each new ADR the next free numeric prefix.

An ADR describes the decision that was true at its date. When the architecture changes,
preserve the historical reason and add an explicit supersession note or a replacement ADR;
do not leave obsolete instructions looking current.

## Consequences

- Current guides link to the active decision.
- Historical plans identify the architecture that superseded them.
- Code and documentation changes that alter a major boundary include an ADR review.
- ADRs never override the current implementation, tests, or security requirements.
