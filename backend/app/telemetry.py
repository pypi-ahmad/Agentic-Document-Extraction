"""OpenTelemetry setup for the extraction pipeline.

This module wires the OpenTelemetry SDK, the OTLP exporter (for
Phoenix or any other OTLP-compatible backend), and the LangChain /
LangGraph auto-instrumentation. It is intentionally small and
degrades gracefully when the OTel packages are not installed —
the rest of the app keeps working, just without distributed
traces.

Span strategy
-------------

- **LangChain / LangGraph** is auto-instrumented by
  ``openinference-instrumentation-langchain`` (the Phoenix-native
  instrumentor). Every LLM call, prompt-template, retriever, and
  tool call gets a span with the OpenInference semantic attributes
  (``llm.model_name``, ``llm.token_count.prompt``, etc.).
- **OCR calls** are wrapped in a manual ``ocr.parse`` span with the
  provider and file size as attributes.
- **Validation + reflection** are wrapped in a manual
  ``extraction.validate`` / ``extraction.reflect`` span so that
  the trace shows the full pipeline shape.

To disable telemetry, set ``OTEL_SDK_DISABLED=true`` in the
environment. The setup is a no-op in that case.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.config import settings
from app.logging_setup import get_logger

logger = get_logger("app.telemetry")


_initialised = False
_tracer_provider: Any = None
_langchain_instrumented = False


def is_enabled() -> bool:
    """Return True when telemetry setup is configured to run."""
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes"):
        return False
    return bool(settings.otel_exporter_otlp_endpoint)


def setup_telemetry() -> None:
    """Initialize OTel SDK + exporters. Idempotent.

    Safe to call from the FastAPI lifespan on every startup; the
    underlying SDK is set up exactly once per process.
    """
    global _initialised, _tracer_provider, _langchain_instrumented
    if _initialised:
        return
    if not is_enabled():
        logger.info("telemetry.disabled (OTEL_SDK_DISABLED or no endpoint configured)")
        _initialised = True
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning("telemetry.deps_missing: %s", exc)
        _initialised = True
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.otel_service_version,
            "deployment.environment": settings.otel_deployment_environment,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=settings.otel_exporter_insecure,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    # Auto-instrument LangChain / LangGraph so every LLM call and
    # graph step gets traced. The OpenInference instrumentor
    # is the canonical Phoenix-compatible one.
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument()
        _langchain_instrumented = True
    except ImportError:
        logger.info("telemetry.openinference_missing (skipping LangChain auto-instrumentation)")
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("telemetry.langchain_instrument_failed: %s", exc)

    logger.info(
        "telemetry.enabled",
        endpoint=settings.otel_exporter_otlp_endpoint,
        service=settings.otel_service_name,
        insecure=settings.otel_exporter_insecure,
        langchain_instrumented=_langchain_instrumented,
    )
    _initialised = True


def shutdown_telemetry() -> None:
    """Flush and shut down the tracer provider. Idempotent."""
    global _initialised, _tracer_provider, _langchain_instrumented
    if not _initialised or _tracer_provider is None:
        return
    try:
        _tracer_provider.shutdown()
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("telemetry.shutdown_failed: %s", exc)
    _tracer_provider = None
    _langchain_instrumented = False
    _initialised = False


def get_tracer(name: str) -> Any:
    """Return an OTel tracer, or a no-op if telemetry is disabled.

    The no-op tracer still supports the ``start_as_current_span``
    context manager API, so call sites can use it without a guard.
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


class _NoopSpan:
    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def set_attribute(self, *args: Any, **kwargs: Any) -> None:
        return None

    def record_exception(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        return None

    def end(self, *args: Any, **kwargs: Any) -> None:
        return None


class _NoopTracer:
    def start_as_current_span(self, *args: Any, **kwargs: Any) -> _NoopSpan:
        return _NoopSpan()


@contextmanager
def manual_span(name: str, **attributes: Any) -> Iterator[_NoopSpan]:
    """Context manager that opens a manual OTel span, or a no-op if
    telemetry is disabled.

    Usage::

        with manual_span("ocr.parse", provider=provider, bytes=size) as span:
            result = await provider.extract_text(file_path)
            span.set_attribute("ocr.pages", len(result.pages))
    """
    tracer = attributes.pop("_tracer", None) or get_tracer("agentic-document-extraction")
    if hasattr(tracer, "start_as_current_span"):
        try:
            with tracer.start_as_current_span(name) as span:
                for k, v in attributes.items():
                    with contextlib.suppress(Exception):  # defensive
                        span.set_attribute(k, v)
                yield span
                return
        except Exception:  # pragma: no cover — defensive
            pass
    span = _NoopSpan()
    yield span


__all__ = [
    "get_tracer",
    "is_enabled",
    "manual_span",
    "setup_telemetry",
    "shutdown_telemetry",
]
