# Deployment

Paperplane 5.3.0 supports local, single-user use. The supported one-file entry points are
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

Uploads, active results, Organize form values, page selections, and Cost totals live only
in the current Streamlit browser session. Page navigation preserves them, but they are not
durable job records. **New parse** keeps Cost totals; **Stop and clear**, restart, or
session end removes the session data.

Cloud AI transmits only selected pages, but that content leaves the machine. Agnes receives
selected images inline without public hosting. Ollama, Docling, PDF Inspector, SQLite, and
artifact storage remain local.

Operators are responsible for the documents they process, permission to process them,
provider selection and terms, credentials, charges, regulatory obligations, output review,
and deletion of retained artifacts. Paperplane is self-hosted; the project maintainers do
not receive documents or API keys through the application.

Required Docling, RapidOCR, and PP-DocLayoutV3 weights are kept in Paperplane's versioned
user data store. Setup migrates an existing cache when possible and downloads only missing
files; subsequent launches validate path and size without network access. The store is
outside the checkout, virtual environment, job store, and Streamlit cache and is deleted
only manually. Ollama's model store is not modified. PP-DocLayoutV3 is loaded locally on
CPU. Ollama OCR crops remain local and are sent only to the configured Ollama
server; keep `OLLAMA_BASE_URL` on loopback when local-only processing is required.
