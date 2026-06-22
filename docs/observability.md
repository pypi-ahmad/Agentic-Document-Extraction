# Observability

This document is the v0.4.0 reference for the observability
stack: OpenTelemetry, the OTLP gRPC exporter, and the
Phoenix self-hosted trace UI.

## What's in v0.4.0

- **OpenTelemetry SDK + OTLP gRPC exporter** wired in
  `backend/app/telemetry.py`. Idempotent setup; graceful
  no-op when OTel packages are not installed.
- **Phoenix service** in `docker-compose.yml`. Open
  `http://localhost:6006` to see the trace UI; the collector
  accepts OTLP gRPC on port 4317.
- **LangChain / LangGraph auto-instrumentation** via
  `openinference-instrumentation-langchain` (Phoenix's
  preferred instrumentor). Every LLM call, prompt template,
  retriever, and tool call gets a span with the OpenInference
  semantic attributes.
- **Manual spans** on OCR (`ocr.parse`), validation
  (`extraction.validate`), and reflection rounds. The full
  pipeline shape shows up as a single trace.

## How to enable

1. Start the Phoenix service: `docker compose up phoenix`.
2. Set the OTLP endpoint in `.env`:
   ```
   OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:4317
   OTEL_EXPORTER_INSECURE=true
   ```
3. Start the app as usual (`just dev` or `docker compose up app`).

The setup is automatic on app startup; no code changes are
needed. Set `OTEL_SDK_DISABLED=true` to skip telemetry
entirely (useful for local dev when Phoenix is not running).

## Settings

In `Settings`:

- `otel_exporter_otlp_endpoint: str = ""` — empty disables.
- `otel_exporter_insecure: bool = True` — set False in
  production behind TLS.
- `otel_service_name: str = "agentic-document-extraction"`.
- `otel_service_version: str = "0.4.0"`.
- `otel_deployment_environment: str = "dev"`.

## Span conventions

- `ocr.parse` — manual span around the OCR provider call.
  Attributes: `ocr_provider`, `file_size`.
- `extraction.validate` — manual span around the validation
  pass. Attributes: `verdict` (`valid` or `needs_review`),
  `invalid_fields`, `total_fields`.
- LangChain spans — auto-instrumented. Look for `llm.`,
  `prompt.`, `retriever.`, `tool.` prefix names in the UI.
- LangGraph spans — auto-instrumented by the OpenInference
  LangChain instrumentor. The full graph run shows as a
  parent trace; each node is a child span.

## What you'll see in the UI

A typical trace for a single extraction:

```
extraction.run (root)
├── triage
├── ocr.parse
├── extract (LangChain)
│   ├── prompt.format
│   ├── llm.openai.chat (or ollama.chat)
│   └── output.parse
├── extraction.validate
├── reflect (if needed)
│   ├── prompt.format
│   └── llm.openai.chat
└── finalize
```

The trace shows:

- **Total latency** end-to-end.
- **Per-step latency** (where the slow parts are).
- **LLM token counts** (prompt + completion) per call.
- **OCR provider + file size** attributes.
- **Validation verdict** at a glance.

## Disabling

To turn off telemetry without removing the code:

- Set `OTEL_SDK_DISABLED=true` in the environment, or
- Set `OTEL_EXPORTER_OTLP_ENDPOINT=""` in `.env`.

Both are graceful no-ops; the rest of the app keeps working.
