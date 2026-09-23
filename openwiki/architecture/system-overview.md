---
type: Architecture
title: Paperplane system overview
description: How the local Streamlit workspace, parsing package, session state, and durable job store fit together.
tags: [architecture, streamlit, data-flow]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T15:07:44.901Z
sources:
  - id: openwiki-source-189d62570c2f36624ef6e5e5
    resource: repo://app_pages/cost.py
  - id: openwiki-source-194ee3efe7532bf6f1a3917d
    resource: repo://app_pages/jobs.py
  - id: openwiki-source-06643b6801b74f288c9371f8
    resource: repo://app_pages/organize.py
  - id: openwiki-source-541a9e49a6db4313a22a5ad3
    resource: repo://paperplane/runtime.py
  - id: openwiki-source-262fdcf12bf066c90575bf3b
    resource: repo://paperplane/shutdown.py
  - id: openwiki-source-964922c41d4be25ac5f159ec
    resource: repo://streamlit_app.py
  - id: openwiki-source-30007c902df0a151cd03e9b3
    resource: repo://workspace_app.py
generated: { by: "codex", at: "2026-09-23T15:07:44.901Z" }
---

# Paperplane system overview

Paperplane is organized around one Streamlit workspace and a Python package that performs parsing and builds outputs. `workspace_app.py` registers four pages: Parse, Organize, Jobs, and Cost. The Parse page coordinates uploads and controls, then delegates document processing to `paperplane.runtime`.

## Main request path

1. The Parse page captures uploaded bytes and the selected engine, model, quality mode, and page range.
2. `runtime.parse_documents` bounds batch size and concurrency, creates one per-file task, and isolates parse failures into individual outcomes.
3. `runtime.parse_document` composes the selected adapters and an `AgenticDocumentParser`. The parser validates and selects pages, invokes the local parser or vision processor as needed, then assembles a `ParseResponse`.
4. The Parse page keeps outcomes and generated previews in Streamlit session state. It also stores job records and artifacts locally.
5. Organize consumes successful `ParseResponse` objects from that same session. Jobs reads the local history store. Cost aggregates provider-reported usage kept in session state.

See [Parse workflow and grounded assembly](../workflows/parse-document.md) for the detailed document path and [job storage and lifecycle](job-storage-and-lifecycle.md) for the boundary between session results and retained job artifacts.

## Ownership by layer

- `workspace_app.py` owns navigation, shared session initialization, and the Stop and clear control.
- `streamlit_app.py` owns the Parse page: engine selection, uploads, batch progress, rendering, downloads, and persistence of job outcomes.
- `paperplane.runtime` composes the selected processing strategy and runs single-document or bounded batch parsing.
- `paperplane.parser` handles input validation, page selection, calls to native parsers and vision processing, and creation of the final response.
- `paperplane.contracts` defines the internal grounded response. `paperplane.ade_contracts` converts it into the exported JSON forms.
- `app_pages/organize.py`, `app_pages/jobs.py`, and `app_pages/cost.py` expose workflows over Parse results, local job history, and session token usage respectively.

## State boundaries

Parse outcomes, selected documents, previews, and session cost totals live in `st.session_state`. Job metadata is stored in SQLite and files are stored under a per-job artifact directory in the user's local Paperplane data folder. These are separate lifecycles: clearing or navigating the browser session does not by itself delete retained job artifacts.

Stop and clear removes Streamlit caches and session data, notifies other Paperplane tabs to leave the UI, and schedules a process exit. The confirmation text states that downloaded models and retained job history and artifacts are preserved.

## Related pages

- [Quickstart and navigation](../quickstart.md)
- [Parse workflow and grounded assembly](../workflows/parse-document.md)
- [Local job storage and lifecycle](job-storage-and-lifecycle.md)
- [Setup and model storage](../operations/setup-and-model-store.md)
