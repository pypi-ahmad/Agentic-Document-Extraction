# Migration from Paperplane 4.2 to 5.0

Version 5 changes the UI, public export contract, and retention model.

- Launch `workspace_app.py`, not `streamlit_app.py`; `Paperplane.cmd` is already updated.
- Replace the five strategy selector with one of four exclusive engines: Docling,
  PDF Inspector, Cloud AI, or Ollama. Combined behavior is the separate cloud-enhancement
  toggle.
- Do not assume Docling is selected by default; all engines start off.
- Use the strict ADE v2 JSON download for compatibility-shaped output, or Paperplane JSON
  for words, confidence state, provenance, warnings, and cross-page relations.
- Job data is no longer session-only. It is retained for seven days in
  `%LOCALAPPDATA%\Paperplane` and can be deleted from Jobs.
- The schema Extract workspace has been removed from current builds. Use Organize for
  Classify, Split, and Section workflows.
- Configure `OLLAMA_BASE_URL` when the local server is not at
  `http://127.0.0.1:11434`.
- Agnes private visual Parse/enhancement now sends images inline; no public image URL is
  required.

The internal `ParseResponse` remains available for engine code. External consumers should
use `paperplane.ade_contracts` exports. There is still no REST endpoint in v5.
