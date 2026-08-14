# v3.0.0 — Stateless Document Extraction

Paperplane is now a deliberately simple, stateless document parser.

## Highlights

- Upload a PDF or image and receive grounded Markdown and hierarchical JSON in one request.
- Choose Fast, Balanced, or Audit processing.
- Launch the FastAPI and Next.js app by double-clicking `Paperplane.cmd` on Windows.
- Run without an application database, migration process, worker, queue, or data volume.
- Keep uploads and results under caller control; Paperplane does not retain them.

## Breaking changes

- Replace create-and-poll clients with synchronous `POST /v2/parse`.
- Job, history, artifact, cancellation, resume, saved-schema, review, curation, batch, and
  reprocessing endpoints have been removed.
- Interrupted requests must be retried by the caller.

See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for the client migration.
