# Quality model

Paperplane combines a structured visual draft with deterministic grounding and bounded
verification. It favors explicit warnings and unresolved values over unsupported guesses.

Quality checks cover reading order, geometry, overlap, duplicate content, tables, uncovered
ink, and source-coordinate alignment. Balanced and Audit modes spend progressively larger
verification budgets on ambiguous evidence.

The contract exposes grounding and failed-page metadata so callers can review evidence.
These signals do not prove correctness; evaluate the app on representative documents and
retain human review for consequential decisions.

The offline test suite covers contracts, parsing helpers, security boundaries, and frontend
behavior. Live model quality depends on the configured endpoint and model versions and must
be measured separately on a locked corpus.
