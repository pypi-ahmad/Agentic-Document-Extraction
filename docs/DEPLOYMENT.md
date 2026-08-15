# Deployment

Paperplane 5.1.1 supports local, single-user use. The supported one-file entry points are
`Paperplane.cmd` on Windows and `Paperplane.sh` on Linux. Both repair missing or out-of-date
prerequisites when possible and otherwise launch `workspace_app.py` directly on
`127.0.0.1:8551`. Automatic Linux system-package installation is limited to APT-based
Ubuntu/Debian systems; other distributions must provide LibreOffice.

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

The PP-DocLayoutV3 weights are downloaded from Hugging Face during setup and then loaded
locally on CPU. Ollama OCR crops remain local and are sent only to the configured Ollama
server; keep `OLLAMA_BASE_URL` on loopback when local-only processing is required.
