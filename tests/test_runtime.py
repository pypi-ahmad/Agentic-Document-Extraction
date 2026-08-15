from io import BytesIO

import pytest
from PIL import Image

import paperplane.runtime as runtime
from paperplane.contracts import AgenticPageInput, assemble_parse_response
from paperplane.ollama_document import OllamaRequestError
from paperplane.runtime import BatchParseRequest, parse_document


@pytest.mark.asyncio
async def test_runtime_requires_key_only_for_pixel_based_input() -> None:
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        await parse_document(
            data=output.getvalue(),
            filename="sample.png",
            model="paperplane-ade-latest",
            api_key="",
            ai_model="gpt-5.6-luna",
        )


@pytest.mark.asyncio
async def test_runtime_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="Unsupported processing model"):
        await parse_document(
            data=b"data",
            filename="sample.pdf",
            model="unknown",
            api_key="test-key",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ai_model", "key_name"),
    [
        ("grok-4.6", "XAI_API_KEY"),
        ("gemini-3.5-flash-lite", "GEMINI_API_KEY"),
        ("gemini-3.6-flash", "GEMINI_API_KEY"),
        ("claude-sonnet-5", "ANTHROPIC_API_KEY"),
        ("agnes-2.5-flash", "AGNES_API_KEY"),
    ],
)
async def test_runtime_names_selected_provider_key_for_pixel_input(
    ai_model: str, key_name: str
) -> None:
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    with pytest.raises(ValueError, match=key_name):
        await parse_document(
            data=output.getvalue(),
            filename="sample.png",
            model="paperplane-ade-latest",
            api_key="",
            ai_model=ai_model,
        )


@pytest.mark.asyncio
async def test_runtime_rejects_unknown_ai_model() -> None:
    with pytest.raises(ValueError, match="Unsupported AI model"):
        await parse_document(
            data=b"data",
            filename="sample.pdf",
            model="paperplane-ade-latest",
            api_key="test-key",
            ai_model="imaginary-model",
        )


@pytest.mark.asyncio
async def test_batch_runtime_limits_concurrency_and_isolates_failures(monkeypatch) -> None:
    active = 0
    peak = 0

    async def fake_parse_document(**kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await __import__("asyncio").sleep(0.01)
        active -= 1
        if kwargs["filename"] == "bad.pdf":
            raise ValueError("bad document")
        return assemble_parse_response(
            document_id=kwargs["filename"],
            job_id=kwargs["filename"],
            model=kwargs["model"],
            pages=[AgenticPageInput(page_number=1)],
        )

    monkeypatch.setattr(runtime, "parse_document", fake_parse_document)
    requests = [
        BatchParseRequest(
            file_id=str(index),
            data=b"pdf",
            filename="bad.pdf" if index == 7 else f"{index}.pdf",
            model="paperplane-ade-latest",
            api_key="",
        )
        for index in range(8)
    ]

    outcomes = await runtime.parse_documents(requests, max_concurrency=3)

    assert peak == 3
    assert [outcome.file_id for outcome in outcomes] == [str(index) for index in range(8)]
    assert outcomes[-1].error == "bad document"
    assert all(outcome.result is not None for outcome in outcomes[:-1])


@pytest.mark.asyncio
async def test_batch_runtime_surfaces_safe_ollama_error(monkeypatch) -> None:
    async def fake_parse_document(**_kwargs):
        raise OllamaRequestError("DeepSeek OCR stopped after three consecutive region failures")

    monkeypatch.setattr(runtime, "parse_document", fake_parse_document)
    outcome = (
        await runtime.parse_documents(
            [
                BatchParseRequest(
                    file_id="deepseek",
                    data=b"pdf",
                    filename="sample.pdf",
                    model="paperplane-ade-latest",
                    api_key="",
                    strategy="ollama",
                )
            ]
        )
    )[0]

    assert outcome.error == "DeepSeek OCR stopped after three consecutive region failures"
