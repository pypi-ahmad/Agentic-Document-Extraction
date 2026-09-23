---
type: Architecture
title: Local job storage and lifecycle
description: How Paperplane stores job metadata and artifacts, how the Jobs page manages retained records, and how checkpoint support differs from the active parse flow.
tags: [architecture, persistence, jobs]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T15:07:44.901Z
sources:
  - id: openwiki-source-194ee3efe7532bf6f1a3917d
    resource: repo://app_pages/jobs.py
  - id: openwiki-source-7c590b991a3be653f7378649
    resource: repo://paperplane/jobs.py
  - id: openwiki-source-964922c41d4be25ac5f159ec
    resource: repo://streamlit_app.py
generated: { by: "codex", at: "2026-09-23T15:07:44.901Z" }
---

# Local job storage and lifecycle

## Storage boundary

Paperplane places `paperplane.sqlite3` and an `artifacts/` directory under `%LOCALAPPDATA%\Paperplane` on Windows, falling back to the user's local application-data directory when `LOCALAPPDATA` is unset. Each job has a UUID, metadata row, and artifact subdirectory. SQLite uses WAL mode so the UI can read while a result is being written.

The record tracks the filename, selected engine, page range, status, timestamps, checkpoint page, result summary, and error. Per-job files can include the original upload, `result.json`, an annotated PDF, and a checkpoint when one is written.

## Parse lifecycle used by the Streamlit page

When the user starts a batch, the Parse page creates one job per uploaded file, marks each job as running, and saves that file under its job directory. Parsing then runs through `runtime.parse_documents` in the Streamlit process. For each outcome, the page either marks the job failed or saves the Paperplane v5 result and any annotated PDF before marking it completed.

This integration retains history and output artifacts. It does not make parsing a background worker that continues after the Streamlit process stops.

## Checkpoints and recovery

`JobStore` provides methods to write a checkpoint file and read it back. `DurableJobService` can pass a saved checkpoint to a worker and record the worker's completion or failure. The active Parse page does not use that service or call the checkpoint methods; its batch loop calls `JobStore` directly. A retained job row therefore does not mean the interrupted parse will resume automatically.

The Jobs page offers a Cancel action for records marked pending or running. The action changes the stored status to `cancelled`; it does not send a cancellation signal to the parse coroutine. Users can also delete one job or clear all retained jobs, which removes their artifact directories.

## Retention

The store purges jobs whose `updated_at` timestamp is older than its configured TTL. The Parse and Jobs pages create the store with a seven-day TTL and purge expired jobs when each page runs.

## Related pages

- [System overview](system-overview.md)
- [Setup and model storage](../operations/setup-and-model-store.md)
- [CI, tests, and benchmark validation](../testing/CI-tests-and-benchmark.md)
