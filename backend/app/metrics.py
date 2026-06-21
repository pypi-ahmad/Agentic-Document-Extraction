"""Prometheus metrics.

A single ``MetricsRegistry`` exposes:
- counters for extraction lifecycle events and review decisions;
- histograms for end-to-end extraction duration and per-step duration;
- a gauge for in-flight jobs.

Use ``/metrics`` in production to scrape. The endpoint is registered
unconditionally so the test suite can hit it.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


class Metrics:
    """Strongly-typed façade over the default Prometheus registry."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)

        self.extractions_total = Counter(
            "ade_extractions_total",
            "Total extractions started, labelled by terminal status.",
            labelnames=("status",),
            registry=self.registry,
        )
        self.reviews_total = Counter(
            "ade_reviews_total",
            "Total reviews submitted, labelled by decision.",
            labelnames=("decision",),
            registry=self.registry,
        )
        self.uploads_total = Counter(
            "ade_uploads_total",
            "Total documents uploaded, labelled by file type and outcome.",
            labelnames=("file_type", "outcome"),
            registry=self.registry,
        )
        self.in_flight_jobs = Gauge(
            "ade_in_flight_jobs",
            "Extractions currently being processed.",
            registry=self.registry,
        )
        self.extraction_duration_seconds = Histogram(
            "ade_extraction_duration_seconds",
            "End-to-end extraction duration in seconds (started_at to completed_at).",
            buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
            registry=self.registry,
        )
        self.llm_call_duration_seconds = Histogram(
            "ade_llm_call_duration_seconds",
            "Per-call LLM duration in seconds.",
            buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
            registry=self.registry,
        )
        self.ocr_call_duration_seconds = Histogram(
            "ade_ocr_call_duration_seconds",
            "Per-call OCR duration in seconds.",
            buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
            registry=self.registry,
        )
        self.provider_errors_total = Counter(
            "ade_provider_errors_total",
            "Provider errors, labelled by provider and category.",
            labelnames=("provider", "category"),
            registry=self.registry,
        )
        self.reflection_attempts_total = Counter(
            "ade_reflection_attempts_total",
            "Reflection loop re-extractions (one increment per successful reflect round).",
            registry=self.registry,
        )

    def render(self) -> tuple[bytes, str]:
        """Return the Prometheus text-format payload and content type."""
        return generate_latest(self.registry), CONTENT_TYPE_LATEST


metrics = Metrics()
