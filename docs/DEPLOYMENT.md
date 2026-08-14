# Deployment

Paperplane 5.0.1 supports local, single-user use. The supported Windows entry point is
`Paperplane.cmd`, which repairs missing or out-of-date prerequisites when necessary and
otherwise launches `workspace_app.py` directly on `127.0.0.1:8551`.

Do not expose the Streamlit port to an untrusted network. There is no authentication,
tenant isolation, REST API, container image, or hosted deployment profile. XSRF protection
remains enabled and telemetry disabled in `.streamlit/config.toml`.

SQLite job metadata and private artifacts live under `%LOCALAPPDATA%\Paperplane` with a
seven-day TTL. Deleting a job removes its artifact directory; **Clear all** removes every
retained job. Provider credentials remain in environment variables/secrets and are never
written to job storage.

Cloud AI transmits only selected pages, but that content leaves the machine. Agnes receives
selected images inline without public hosting. Ollama, Docling, PDF Inspector, SQLite, and
artifact storage remain local.
