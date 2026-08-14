from io import BytesIO
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

import paperplane.runtime as runtime
from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    NormalizedBox,
    assemble_parse_response,
)

APP_PATH = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def test_app_explains_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = AppTest.from_file(APP_PATH).run()

    assert app.title[0].value == "Paperplane"
    assert any("OPENAI_API_KEY" in warning.value for warning in app.warning)
    assert next(button for button in app.button if button.label == "Parse document").disabled


def test_app_allows_local_document_upload_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = AppTest.from_file(APP_PATH).run()
    app.file_uploader[0].set_value(
        (
            "report.docx",
            b"test fixture",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    ).run()

    assert not next(button for button in app.button if button.label == "Parse document").disabled


def test_app_parses_upload_and_exposes_downloads(monkeypatch) -> None:
    async def fake_parse_document(**kwargs):
        assert kwargs["filename"] == "invoice.png"
        assert kwargs["model"] == "paperplane-ade-latest"
        return assemble_parse_response(
            document_id="document",
            job_id="request",
            model=kwargs["model"],
            pages=[
                AgenticPageInput(
                    page_number=1,
                    blocks=[
                        AgenticBlockInput(
                            type="text",
                            markdown="Invoice total: 42",
                            box=NormalizedBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                        )
                    ],
                )
            ],
            duration_ms=25,
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runtime, "parse_document", fake_parse_document)
    app = AppTest.from_file(APP_PATH).run()
    app.file_uploader[0].set_value(("invoice.png", _png(), "image/png")).run()
    next(button for button in app.button if button.label == "Parse document").click().run()

    assert any(metric.label == "Pages" and metric.value == "1" for metric in app.metric)
    assert any("Invoice total: 42" in item.value for item in app.markdown)
    assert [tab.label for tab in app.tabs] == ["Output", "Annotated PDF", "Markdown", "JSON"]
    assert {button.label for button in app.download_button} == {
        "Download Markdown",
        "Download annotated PDF",
        "Download JSON",
    }

    app.session_state["result_view"] = "Annotated PDF"
    app.run()
    assert any("grounded blocks" in caption.value for caption in app.caption)

    app.session_state["result_view"] = "Markdown"
    app.run()
    assert any("Invoice total: 42" in code.value for code in app.code)

    app.session_state["result_view"] = "JSON"
    app.run()
    assert app.json
