---
type: Guide
title: Paperplane quickstart and navigation
description: Start the local workspace, run a first parse, and find the workflow or reference page for the next task.
tags: [quickstart, navigation, streamlit]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T15:07:44.901Z
sources:
  - id: openwiki-source-189d62570c2f36624ef6e5e5
    resource: repo://app_pages/cost.py
  - id: openwiki-source-33d83ea58a9d8da61b254adf
    resource: repo://Paperplane.cmd
  - id: openwiki-source-2730258e37f39e7b07bee6d3
    resource: repo://Paperplane.sh
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-30007c902df0a151cd03e9b3
    resource: repo://workspace_app.py
generated: { by: "codex", at: "2026-09-23T15:07:44.901Z" }
---

# Paperplane quickstart and navigation

Start Paperplane with `Paperplane.cmd` on Windows or `./Paperplane.sh` on Linux, then open `http://127.0.0.1:8551`. The launchers prepare the environment and start the local Streamlit workspace.

## First parse

1. Open **Parse** and select one processing engine.
2. If needed, choose a cloud model or installed vision-capable Ollama model. Local engines can optionally use cloud enhancement.
3. Add documents and set each file's page range.
4. Select **Parse files**, review the result, and download individual outputs or the batch ZIP.
5. Continue to **Organize** for Classify, Split, or Section, or open **Jobs** to inspect or delete retained local artifacts.

## Find the right page

- **Setup and models:** [Setup, model storage, and shutdown](operations/setup-and-model-store.md)
- **How parsing works:** [Parse workflow and grounded assembly](workflows/parse-document.md)
- **How outputs are represented:** [Contracts and exported formats](concepts/contracts-and-exports.md)
- **Provider choices and cost:** [Provider catalog and cost reporting](integrations/provider-catalog-and-cost.md)
- **Organize results:** [Classify, Split, and Section](workflows/organize.md)
- **Job persistence:** [Job storage and lifecycle](architecture/job-storage-and-lifecycle.md)
- **System map:** [Paperplane system overview](architecture/system-overview.md)
- **Tests and benchmark checks:** [Tests, CI, and benchmark validation](testing/CI-tests-and-benchmark.md)

The workspace has four pages: Parse, Organize, Jobs, and Cost. Parse, Organize, and Jobs provide document workflows and retained history; Cost reports provider usage accumulated in the current session.
