"""Request, billing, and UI regression checks for the GPT-6 Sol migration."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from paperplane.ingest import RenderedPage
from paperplane.model_catalog import DEFAULT_DOCUMENT_MODEL, DOCUMENT_MODELS, estimate_model_cost
from paperplane.openai_document import (
    OpenAIDocumentAdapter,
    OpenAIRequestError,
    OpenAIUsage,
    StructuredGeneration,
    capture_audit_calls,
)
from paperplane.pipeline import V2PageProcessor, _model_output_overgenerated
from paperplane.pipeline_contracts import ProcessingMode, VerificationStatus
from paperplane.prompt_loader import PROMPT_ROOT, load_prompt
from paperplane.types import BoundingBox, NativeWord


@pytest.mark.parametrize("requested_effort", ["none", "low", "medium", "high"])
async def test_sol_requests_and_audits_use_medium(requested_effort):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test-response",
                "output": [{"content": [{"type": "output_text", "text": '{"text":"42"}'}]}],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 300},
                },
            },
        )

    records = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAIDocumentAdapter(client, api_key="test-only")
        with capture_audit_calls(records):
            generation = await adapter.generate_structured(
                model=DEFAULT_DOCUMENT_MODEL,
                image=b"synthetic-image",
                instructions=load_prompt("figure-description.md"),
                schema_name="read_number",
                schema={"type": "object"},
                reasoning_effort=requested_effort,
                detail="high",
                prompt_cache_key="test",
            )
    payload = requests[0]
    assert payload["model"] == "gpt-6-sol"
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert payload["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
    assert payload["input"][0]["content"][1]["type"] == "input_image"
    assert records[0]["reasoning_effort"] == "medium"
    assert generation.usage.cache_write_tokens == 300
    assert estimate_model_cost(
        DEFAULT_DOCUMENT_MODEL, **generation.usage.model_dump()
    ).total_cost_usd == Decimal("0.00279")


async def test_sol_retries_content_filter_and_reports_omission_warning():
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "id": "filtered-response",
                    "status": "incomplete",
                    "incomplete_details": {"reason": "content_filter"},
                    "output": [{"content": [{"type": "output_text", "text": '{"text":"cut'}]}],
                    "usage": {"input_tokens": 10, "output_tokens": 0},
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "retry-response",
                "status": "completed",
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"text":"[CONTENT OMITTED]"}',
                            }
                        ]
                    }
                ],
                "usage": {"input_tokens": 12, "output_tokens": 4},
            },
        )

    records = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAIDocumentAdapter(client, api_key="test-only")
        with capture_audit_calls(records):
            generation = await adapter.generate_structured(
                model="gpt-6-sol",
                image=None,
                instructions=load_prompt("figure-description.md"),
                schema_name="test",
                schema={"type": "object"},
                reasoning_effort="medium",
                detail="high",
                prompt_cache_key="test",
            )

    assert len(requests) == 2
    assert "[CONTENT OMITTED]" in requests[1]["input"][0]["content"][0]["text"]
    assert requests[1]["input"][0]["content"][0]["text"] == load_prompt("content-filter-retry.md")
    assert generation.value == {"text": "[CONTENT OMITTED]"}
    assert generation.warnings == ["content_filter_retry_used"]
    assert generation.usage.input_tokens == 22
    assert generation.usage.output_tokens == 4
    assert records[0]["content_filter_retry"] is True
    assert records[0]["first_response_id"] == "filtered-response"


async def test_sol_reports_second_content_filter_interruption():
    calls = 0

    def respond(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "id": f"filtered-{calls}",
                "status": "incomplete",
                "incomplete_details": {"reason": "content_filter"},
                "output": [],
            },
        )

    records = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAIDocumentAdapter(client, api_key="test-only")
        with capture_audit_calls(records):
            with pytest.raises(OpenAIRequestError, match="content filter interrupted"):
                await adapter.generate_structured(
                    model="gpt-6-sol",
                    image=None,
                    instructions=load_prompt("figure-description.md"),
                    schema_name="test",
                    schema={"type": "object"},
                    reasoning_effort="medium",
                    detail="high",
                    prompt_cache_key="test",
                )

    assert calls == 2
    assert records[0]["error_type"] == "incomplete_content_filter"


async def test_openai_adapter_normalizes_malformed_output_shape():
    def respond(_request):
        return httpx.Response(200, json={"output": [[], "invalid", {"content": "invalid"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAIDocumentAdapter(client, api_key="test-only")
        with pytest.raises(OpenAIRequestError, match="returned no structured output"):
            await adapter.generate_structured(
                model="gpt-6-sol",
                image=None,
                instructions=load_prompt("figure-description.md"),
                schema_name="test",
                schema={"type": "object"},
                reasoning_effort="medium",
                detail="high",
                prompt_cache_key="test",
            )


async def test_page_processor_uses_native_pdf_text_after_content_filter():
    class FilteredAdapter:
        async def generate_structured(self, **_kwargs):
            raise OpenAIRequestError(
                "OpenAI content filter interrupted structured output",
                usage=OpenAIUsage(input_tokens=20, output_tokens=3),
            )

    page = RenderedPage(
        page_number=1,
        image_png=b"png",
        width=612,
        height=792,
        native_words=[
            NativeWord(
                text="Member",
                bbox=BoundingBox(left=0.1, top=0.1, right=0.2, bottom=0.12),
            ),
            NativeWord(
                text="information",
                bbox=BoundingBox(left=0.21, top=0.1, right=0.35, bottom=0.12),
            ),
        ],
    )

    result = await V2PageProcessor(FilteredAdapter()).process_page(
        source=b"pdf",
        filename="form.pdf",
        source_sha256="0" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    assert result.markdown == "Member information"
    assert result.warnings == ["openai_content_filter_native_pdf_fallback"]
    assert result.input_tokens == 20
    assert result.output_tokens == 3
    assert result.chunks[0].source_model == "native_pdf"
    assert result.chunks[0].verification_status == VerificationStatus.VERIFIED


async def test_page_processor_uses_grounded_ocr_lines_after_content_filter(monkeypatch):
    class FilteredAdapter:
        async def generate_structured(self, **_kwargs):
            raise OpenAIRequestError("OpenAI content filter interrupted structured output")

    observed = [
        NativeWord(
            text="First",
            bbox=BoundingBox(left=0.1, top=0.1, right=0.2, bottom=0.12),
        ),
        NativeWord(
            text="line",
            bbox=BoundingBox(left=0.21, top=0.1, right=0.3, bottom=0.12),
        ),
        NativeWord(
            text="Second",
            bbox=BoundingBox(left=0.1, top=0.2, right=0.22, bottom=0.22),
        ),
    ]
    monkeypatch.setattr(
        "paperplane.pipeline.extract_ocr_words",
        lambda _image: [(word, 0.9) for word in observed],
    )
    page = RenderedPage(
        page_number=1,
        image_png=b"png",
        width=612,
        height=792,
        native_words=[],
    )

    result = await V2PageProcessor(FilteredAdapter()).process_page(
        source=b"pdf",
        filename="scan.pdf",
        source_sha256="0" * 64,
        page=page,
        mode=ProcessingMode.BALANCED,
    )

    assert result.markdown == "First line\nSecond"
    assert len(result.chunks) == 2
    assert result.warnings == ["openai_content_filter_local_ocr_fallback"]
    assert all(chunk.source_model == "local_ocr" for chunk in result.chunks)
    assert all(chunk.verification_status == VerificationStatus.CANDIDATE for chunk in result.chunks)


def test_overgeneration_guard_compares_model_output_with_local_evidence():
    evidence = [
        NativeWord(
            text=f"word-{index}",
            bbox=BoundingBox(left=0.1, top=0.1, right=0.2, bottom=0.2),
        )
        for index in range(100)
    ]

    assert _model_output_overgenerated("<td>word</td>" * 501, evidence)
    assert not _model_output_overgenerated("word " * 499, evidence)
    assert not _model_output_overgenerated("word " * 501, evidence * 2)


async def test_page_processor_replaces_overgenerated_model_page(monkeypatch):
    class OvergeneratingAdapter:
        async def generate_structured(self, **_kwargs):
            repeated = "word " * 501
            return StructuredGeneration(
                value={
                    "chunks": [
                        {
                            "type": "text",
                            "text": repeated,
                            "markdown": repeated,
                            "box": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.9},
                            "parent_order": None,
                            "atomic_lines": [],
                            "row": None,
                            "col": None,
                            "rowspan": 1,
                            "colspan": 1,
                        }
                    ]
                },
                usage=OpenAIUsage(input_tokens=10, output_tokens=20),
                latency_ms=1,
            )

    monkeypatch.setattr(
        "paperplane.pipeline.assess_page_quality",
        lambda _chunks, _image: type(
            "Assessment", (), {"flagged": False, "reasons": (), "uncovered_ink_ratio": 0.0}
        )(),
    )
    evidence = [
        NativeWord(
            text=f"observed-{index}",
            bbox=BoundingBox(
                left=0.1,
                top=0.1 + index * 0.01,
                right=0.2,
                bottom=0.105 + index * 0.01,
            ),
        )
        for index in range(10)
    ]
    page = RenderedPage(
        page_number=1,
        image_png=b"png",
        width=612,
        height=792,
        native_words=evidence,
    )

    result = await V2PageProcessor(OvergeneratingAdapter()).process_page(
        source=b"pdf",
        filename="form.pdf",
        source_sha256="0" * 64,
        page=page,
        mode=ProcessingMode.ECONOMY,
    )

    assert len(result.markdown.split()) == 10
    assert result.warnings == ["model_output_overgeneration_local_text_fallback"]
    assert all(chunk.source_pass == "overgeneration_fallback" for chunk in result.chunks)
    assert result.input_tokens == 10
    assert result.output_tokens == 20


async def test_page_markdown_does_not_repeat_grounded_table_cells(monkeypatch):
    table = {
        "type": "table",
        "text": "Name Value",
        "markdown": "<table><tr><td>Name</td><td>Value</td></tr></table>",
        "box": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.4},
        "parent_order": None,
        "atomic_lines": [],
        "row": None,
        "col": None,
        "rowspan": None,
        "colspan": None,
    }
    cells = [
        {
            "type": "table_cell",
            "text": value,
            "markdown": value,
            "box": {"left": left, "top": 0.1, "right": right, "bottom": 0.4},
            "parent_order": 1,
            "atomic_lines": [],
            "row": 0,
            "col": column,
            "rowspan": 1,
            "colspan": 1,
        }
        for column, (value, left, right) in enumerate([("Name", 0.1, 0.5), ("Value", 0.5, 0.9)])
    ]

    class TableAdapter:
        async def generate_structured(self, **_kwargs):
            return StructuredGeneration(
                value={"chunks": [table, *cells]},
                usage=OpenAIUsage(input_tokens=10, output_tokens=20),
                latency_ms=1,
            )

    monkeypatch.setattr(
        "paperplane.pipeline.assess_page_quality",
        lambda _chunks, _image: type(
            "Assessment", (), {"flagged": False, "reasons": (), "uncovered_ink_ratio": 0.0}
        )(),
    )
    result = await V2PageProcessor(TableAdapter()).process_page(
        source=b"pdf",
        filename="form.pdf",
        source_sha256="0" * 64,
        page=RenderedPage(
            page_number=1,
            image_png=b"png",
            width=612,
            height=792,
            native_words=[],
        ),
        mode=ProcessingMode.ECONOMY,
    )

    assert len(result.chunks) == 3
    assert result.markdown == table["markdown"]
    assert [chunk.parent_id for chunk in result.chunks[1:]] == [result.chunks[0].id] * 2


@pytest.mark.parametrize("requested,expected", [("none", "low"), ("high", "high")])
async def test_xai_keeps_its_reasoning_and_cache_behavior(requested, expected):
    def respond(request):
        payload = json.loads(request.content)
        assert payload["reasoning"] == {"effort": expected}
        assert "prompt_cache_options" not in payload
        assert "prompt_cache_breakpoint" not in payload["input"][0]["content"][0]
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": "{}"}]}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAIDocumentAdapter(
            client,
            api_key="test-only",
            provider_name="xAI",
            explicit_prompt_cache=False,
            minimum_reasoning_effort="low",
        )
        await adapter.generate_structured(
            model="grok-4.6",
            image=None,
            instructions=load_prompt("figure-description.md"),
            schema_name="test",
            schema={"type": "object"},
            reasoning_effort=requested,
            detail="high",
            prompt_cache_key="test",
        )


def test_model_prompts_are_markdown_files():
    prompt_files = list(PROMPT_ROOT.iterdir())

    assert prompt_files
    assert all(path.is_file() and path.suffix == ".md" for path in prompt_files)
    assert all(path.read_text(encoding="utf-8").strip() for path in prompt_files)


@pytest.mark.parametrize(
    "input_tokens,cached,written,output_tokens,expected",
    [
        (1000, 0, 0, 100, "0.003"),
        (1000, 1000, 0, 0, "0.0002"),
        (1000, 0, 1000, 0, "0.0025"),
        (1000, 200, 300, 100, "0.00279"),
        (0, 0, 0, 0, "0"),
        (-1, -2, -3, -4, "0"),
        (1000, 1200, 1200, 0, "0.0002"),
        (1000, 200, 1200, 0, "0.00204"),
    ],
)
def test_cost_categories(input_tokens, cached, written, output_tokens, expected):
    estimate = estimate_model_cost(
        "gpt-6-sol",
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        cache_write_tokens=written,
        output_tokens=output_tokens,
    )
    assert estimate.total_cost_usd == Decimal(expected)
    assert estimate.total_cost_usd == estimate.input_cost_usd + estimate.output_cost_usd


def test_other_providers_keep_existing_estimates():
    for model in DOCUMENT_MODELS:
        if model.provider == "openai":
            continue
        assert estimate_model_cost(
            model.model_id, input_tokens=1000, output_tokens=100, cache_write_tokens=300
        ) == estimate_model_cost(model.model_id, input_tokens=1000, output_tokens=100)


def test_cost_page_includes_cache_writes():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app_pages/cost.py")
    app.session_state["session_usage"] = {
        "synthetic": {
            "gpt-6-sol": {
                "input_tokens": 1000,
                "cached_input_tokens": 200,
                "cache_write_tokens": 300,
                "output_tokens": 100,
            }
        }
    }
    app.run(timeout=30)
    assert not app.exception
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Cache write tokens"] == "300"
    assert metrics["Estimated cost"] == "$0.002790"
    row = app.dataframe[0].value.iloc[0]
    assert row["Model"] == "GPT-6 Sol"
    assert row["Cache write tokens"] == 300


def test_parse_page_defaults_to_sol(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    app.session_state["engine_cloud_ai"] = True
    app.run(timeout=60)
    assert not app.exception
    selector = app.selectbox(key="cloud_ai_model")
    assert selector.value == "GPT-6 Sol"
    assert len(selector.options) == 6
    selector.select("Grok 4.6").run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="cloud_ai_model").value == "Grok 4.6"
