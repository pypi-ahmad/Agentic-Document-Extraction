# Deployment

Paperplane 4.2.0 supports local, single-user operation only.

## Supported deployment

On Windows 11, double-click `Paperplane.cmd`. It installs `uv` if needed, installs Python
3.12.10, synchronizes `uv.lock`, downloads Docling layout/table models, and starts
Streamlit. Later launches reuse installed tools and model weights while rechecking the
locked environment.

Developers can start the same application directly:

```powershell
uv sync --locked
uv run streamlit run streamlit_app.py --server.port=8551
```

The checked-in Streamlit configuration binds to `127.0.0.1`, enables XSRF protection,
limits uploads to 200 MB, and disables Streamlit usage telemetry.

Vision processing requires outbound HTTPS access to the selected provider. Credentials and
provider APIs are listed in [MODELS.md](MODELS.md); `OPENAI_BASE_URL` is an optional
OpenAI-only override. Native Docling conversion remains local.

## Unsupported deployment

The repository does not ship a container image, reverse-proxy configuration, public server
profile, authentication layer, multi-user isolation, durable storage, or hosted deployment
workflow. Do not expose the Streamlit port to an untrusted network.

A future shared deployment would require explicit designs for authentication,
authorization, TLS, data retention and deletion, concurrency, model-provider privacy,
observability, abuse controls, and resource limits. Local configuration is not a substitute
for those controls.
