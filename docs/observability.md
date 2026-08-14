# Observability

The backend emits structured logs with stable event names and duration fields. Optional
OpenTelemetry setup is initialized during FastAPI lifespan and safely becomes a no-op when
no exporter is configured.

Monitor request count, latency, validation errors, upstream failures, input size/page count,
and model usage. Never log credentials, request authorization headers, source-document
contents, or base64 image payloads.

Use `/health` for process liveness and `/health/ready` to verify that OpenAI parsing is
configured. Because parsing is synchronous, client and proxy latency should be measured as
part of the same request.
