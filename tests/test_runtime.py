from io import BytesIO

import pytest
from PIL import Image

from paperplane.runtime import parse_document


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
