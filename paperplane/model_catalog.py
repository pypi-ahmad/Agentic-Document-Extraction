"""The supported document-model catalog and its credential requirements."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Provider = Literal["xai", "openai", "google", "anthropic", "agnes"]


@dataclass(frozen=True, slots=True)
class DocumentModel:
    label: str
    model_id: str
    provider: Provider
    api_key_env: str
    help_text: str
    docs_url: str
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    cached_input_price_per_million: Decimal | None = None
    pricing_note: str = ""


@dataclass(frozen=True, slots=True)
class ModelCostEstimate:
    input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_cost_usd: Decimal


DOCUMENT_MODELS: tuple[DocumentModel, ...] = (
    DocumentModel(
        label="Grok 4.6",
        model_id="grok-4.6",
        provider="xai",
        api_key_env="XAI_API_KEY",
        help_text="xAI's flagship multimodal model with configurable reasoning.",
        docs_url="https://docs.x.ai/developers/models",
        input_price_per_million=Decimal("2.00"),
        output_price_per_million=Decimal("6.00"),
        pricing_note="Standard rate; fast or very-long-context surcharges are not applied.",
    ),
    DocumentModel(
        label="GPT-5.6 Luna",
        model_id="gpt-5.6-luna",
        provider="openai",
        api_key_env="OPENAI_API_KEY",
        help_text="OpenAI's efficient GPT-5.6 model for high-volume workloads.",
        docs_url="https://developers.openai.com/api/docs/guides/latest-model",
        input_price_per_million=Decimal("0.20"),
        output_price_per_million=Decimal("1.20"),
        cached_input_price_per_million=Decimal("0.02"),
        pricing_note="Configured rate includes the supplied cached-input discount.",
    ),
    DocumentModel(
        label="Gemini 3.5 Flash-Lite",
        model_id="gemini-3.5-flash-lite",
        provider="google",
        api_key_env="GOOGLE_API_KEY",
        help_text="Google's low-latency model optimized for document parsing.",
        docs_url="https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite",
        input_price_per_million=Decimal("0.30"),
        output_price_per_million=Decimal("2.50"),
        pricing_note="Standard rate; Batch API discounts are not applied.",
    ),
    DocumentModel(
        label="Gemini 3.7 Flash",
        model_id="gemini-3.7-flash",
        provider="google",
        api_key_env="GOOGLE_API_KEY",
        help_text="Google's capable Flash model for agentic and multimodal workflows.",
        docs_url="https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash",
        input_price_per_million=Decimal("0.75"),
        output_price_per_million=Decimal("3.75"),
        pricing_note="Promotional standard rate through December 31, 2026.",
    ),
    DocumentModel(
        label="Claude Sonnet 5",
        model_id="claude-sonnet-5",
        provider="anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        help_text="Anthropic's production model balancing intelligence and speed.",
        docs_url="https://platform.claude.com/docs/en/about-claude/models/whats-new-sonnet-5",
        input_price_per_million=Decimal("2.00"),
        output_price_per_million=Decimal("10.00"),
        pricing_note="Configured standard rate; Batch API discounts are not applied.",
    ),
    DocumentModel(
        label="Agnes 2.5 Flash",
        model_id="agnes-2.5-flash",
        provider="agnes",
        api_key_env="AGNES_API_KEY",
        help_text="Agnes AI's OpenAI-compatible multimodal Flash model.",
        docs_url="https://www.agnes-ai.com/en/docs/agnes-25-flash",
        input_price_per_million=Decimal("0"),
        output_price_per_million=Decimal("0"),
        pricing_note="Configured as free.",
    ),
)

DEFAULT_DOCUMENT_MODEL = "gpt-5.6-luna"
DOCUMENT_MODEL_BY_ID = {model.model_id: model for model in DOCUMENT_MODELS}
DOCUMENT_MODEL_BY_LABEL = {model.label: model for model in DOCUMENT_MODELS}


def get_document_model(model_id: str) -> DocumentModel:
    """Return one supported model or reject an unrecognized API identifier."""
    try:
        return DOCUMENT_MODEL_BY_ID[model_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported AI model: {model_id}") from exc


def estimate_model_cost(
    model_id: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> ModelCostEstimate:
    """Estimate one parse at the configured per-million-token rates."""
    model = get_document_model(model_id)
    cached_tokens = min(max(cached_input_tokens, 0), max(input_tokens, 0))
    regular_tokens = max(input_tokens, 0) - cached_tokens
    cached_rate = model.cached_input_price_per_million or model.input_price_per_million
    scale = Decimal("1000000")
    input_cost = (
        Decimal(regular_tokens) * model.input_price_per_million
        + Decimal(cached_tokens) * cached_rate
    ) / scale
    output_cost = Decimal(max(output_tokens, 0)) * model.output_price_per_million / scale
    return ModelCostEstimate(
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + output_cost,
    )


__all__ = [
    "DEFAULT_DOCUMENT_MODEL",
    "DOCUMENT_MODELS",
    "DOCUMENT_MODEL_BY_ID",
    "DOCUMENT_MODEL_BY_LABEL",
    "DocumentModel",
    "ModelCostEstimate",
    "Provider",
    "estimate_model_cost",
    "get_document_model",
]
