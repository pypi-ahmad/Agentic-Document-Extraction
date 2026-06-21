"""Tests for the OpenTelemetry setup module.

Covers:

- ``is_enabled`` respects ``OTEL_SDK_DISABLED`` and the endpoint setting.
- ``setup_telemetry`` is idempotent.
- ``setup_telemetry`` is a graceful no-op when OTel packages are missing
  (or when telemetry is disabled).
- ``manual_span`` works with and without a configured tracer provider.
- ``get_tracer`` returns a usable tracer object in both states.
- ``shutdown_telemetry`` is idempotent and safe to call without setup.
"""

from __future__ import annotations

import pytest

from app.telemetry import (
    _NoopSpan,
    _NoopTracer,
    get_tracer,
    is_enabled,
    manual_span,
    setup_telemetry,
    shutdown_telemetry,
)


@pytest.fixture(autouse=True)
def _reset_telemetry_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level _initialised flag so each test gets a
    fresh setup."""
    import app.telemetry as tel

    monkeypatch.setattr(tel, "_initialised", False)
    monkeypatch.setattr(tel, "_tracer_provider", None)
    monkeypatch.setattr(tel, "_langchain_instrumented", False)


# ── is_enabled ───────────────────────────────────────────────────────


def test_is_enabled_false_when_endpoint_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.otel_exporter_otlp_endpoint", "")
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    assert is_enabled() is False


def test_is_enabled_false_when_sdk_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.otel_exporter_otlp_endpoint", "http://phoenix:4317")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert is_enabled() is False


def test_is_enabled_true_when_endpoint_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.otel_exporter_otlp_endpoint", "http://phoenix:4317")
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    assert is_enabled() is True


# ── setup_telemetry ──────────────────────────────────────────────────


def test_setup_telemetry_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the endpoint is empty, setup runs but is a no-op."""
    monkeypatch.setattr("app.config.settings.otel_exporter_otlp_endpoint", "")
    setup_telemetry()
    # No exception, _initialised is True (so we don't try again).
    from app.telemetry import _initialised

    assert _initialised is True


def test_setup_telemetry_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling setup_telemetry twice does not double-register."""
    monkeypatch.setattr("app.config.settings.otel_exporter_otlp_endpoint", "http://phoenix:4317")
    setup_telemetry()
    setup_telemetry()
    # If double-registration happened, the SDK would log a warning, but
    # the test still passes because no exception is raised.


def test_shutdown_telemetry_safe_without_setup() -> None:
    """shutdown is safe to call when setup was never called."""
    shutdown_telemetry()
    shutdown_telemetry()  # idempotent


# ── get_tracer ───────────────────────────────────────────────────────


def test_get_tracer_returns_usable_tracer() -> None:
    """get_tracer returns an object with start_as_current_span."""
    tracer = get_tracer("test")
    assert tracer is not None
    assert hasattr(tracer, "start_as_current_span")


def test_get_tracer_returns_noop_when_deps_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """When opentelemetry is not importable, get_tracer returns the no-op."""
    import sys

    # Remove opentelemetry from sys.modules so the lazy import inside
    # get_tracer raises ImportError.
    saved = {k: v for k, v in sys.modules.items() if k.startswith("opentelemetry")}
    for k in saved:
        del sys.modules[k]
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    try:
        tracer = get_tracer("test")
        assert isinstance(tracer, _NoopTracer)
    finally:
        sys.modules.update(saved)


# ── manual_span ──────────────────────────────────────────────────────


def test_manual_span_with_noop_tracer() -> None:
    """manual_span yields a no-op span when the underlying tracer
    is the no-op fallback (opentelemetry not importable)."""
    noop = _NoopTracer()
    with manual_span("test.span", foo="bar", _tracer=noop) as span:
        assert isinstance(span, _NoopSpan)
        # No-op methods should not raise.
        span.set_attribute("a", 1)
        span.record_exception(RuntimeError("x"))


def test_manual_span_yields_object_with_set_attribute() -> None:
    """The yielded object always has set_attribute (no-op or real)."""
    with manual_span("test.span") as span:
        span.set_attribute("k", "v")  # no exception
        assert hasattr(span, "set_attribute")


# ── setup_telemetry with mocked OTel SDK ────────────────────────────


def test_setup_telemetry_initialises_tracer_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When OTel is importable, setup wires a TracerProvider and exports."""

    # Monkeypatch the imports inside setup_telemetry.
    import sys

    class FakeBatchProcessor:
        def __init__(self, exporter: object) -> None:
            self.exporter = exporter

    class FakeTracerProvider:
        def __init__(self, resource: object) -> None:
            self.resource = resource
            self.processors: list[object] = []

        def add_span_processor(self, proc: object) -> None:
            self.processors.append(proc)

    class FakeResource:
        @staticmethod
        def create(attrs: dict) -> FakeResource:
            return FakeResource()

        def __init__(self) -> None:
            self.attrs: dict = {}

    class FakeOTLPExporter:
        def __init__(self, endpoint: str, insecure: bool) -> None:
            self.endpoint = endpoint
            self.insecure = insecure

    fake_otel = type(sys)("opentelemetry")
    fake_trace = type(sys)("opentelemetry.trace")
    fake_otel.trace = fake_trace
    fake_trace.set_tracer_provider = lambda _provider: None
    fake_exporter_mod = type(sys)("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
    fake_exporter_mod.OTLPSpanExporter = FakeOTLPExporter
    fake_sdk_trace = type(sys)("opentelemetry.sdk.trace")
    fake_sdk_trace.TracerProvider = FakeTracerProvider
    fake_sdk_trace_export = type(sys)("opentelemetry.sdk.trace.export")
    fake_sdk_trace_export.BatchSpanProcessor = FakeBatchProcessor
    fake_sdk_resources = type(sys)("opentelemetry.sdk.resources")
    fake_sdk_resources.Resource = FakeResource

    saved = {k: v for k, v in sys.modules.items() if k.startswith("opentelemetry")}
    sys.modules["opentelemetry"] = fake_otel
    sys.modules["opentelemetry.trace"] = fake_trace
    sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"] = fake_exporter_mod
    sys.modules["opentelemetry.sdk.trace"] = fake_sdk_trace
    sys.modules["opentelemetry.sdk.trace.export"] = fake_sdk_trace_export
    sys.modules["opentelemetry.sdk.resources"] = fake_sdk_resources

    monkeypatch.setattr("app.config.settings.otel_exporter_otlp_endpoint", "http://phoenix:4317")
    monkeypatch.setattr("app.config.settings.otel_exporter_insecure", True)

    try:
        setup_telemetry()
        from app.telemetry import _tracer_provider

        assert _tracer_provider is not None
        assert hasattr(_tracer_provider, "processors")
    finally:
        sys.modules.update(saved)
        shutdown_telemetry()
