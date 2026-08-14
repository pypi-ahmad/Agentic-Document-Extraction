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
