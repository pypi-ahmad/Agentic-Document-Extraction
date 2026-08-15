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
API_KEY_NAMES = [
    "OPENAI_API_KEY",
    "XAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AGNES_API_KEY",
]


def _clear_api_keys(monkeypatch) -> None:
    for name in API_KEY_NAMES:
        monkeypatch.delenv(name, raising=False)


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def _select_engine(app: AppTest, label: str) -> AppTest:
    return next(item for item in app.toggle if item.label == label).set_value(True).run()


def test_app_explains_missing_api_key(monkeypatch) -> None:
    _clear_api_keys(monkeypatch)
    app = AppTest.from_file(APP_PATH).run()
    app = _select_engine(app, "Cloud AI ADE")
    app.file_uploader[0].set_value([("invoice.png", _png(), "image/png")]).run()

    assert app.title[0].value == "Paperplane"
    assert any("OPENAI_API_KEY" in warning.value for warning in app.warning)
    assert next(button for button in app.button if button.label == "Parse files").disabled


def test_app_allows_local_document_upload_without_api_key(monkeypatch) -> None:
    _clear_api_keys(monkeypatch)
    app = AppTest.from_file(APP_PATH).run()
    app = _select_engine(app, "Docling ADE")
    app.file_uploader[0].set_value(
        [
            (
                "report.docx",
                b"test fixture",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        ]
    ).run()

    assert not next(button for button in app.button if button.label == "Parse files").disabled


def test_app_parses_upload_and_exposes_downloads(monkeypatch) -> None:
    async def fake_parse_document(**kwargs):
        assert kwargs["filename"] == "invoice.png"
        assert kwargs["model"] == "paperplane-ade-latest"
        assert kwargs["ai_model"] == "gpt-5.6-luna"
        assert kwargs["strategy"] == "ai"
        assert kwargs["page_start"] == 1
        assert kwargs["page_end"] == 1
        assert kwargs["openai_base_url"] == "https://openai.example/v1"
        return assemble_parse_response(
            document_id="document",
            job_id="request",
            model=kwargs["model"],
            ai_model=kwargs["ai_model"],
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cached_input_tokens=250_000,
            processing_strategy="ai",
            source_page_count=1,
            page_range=(1, 1),
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
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example/v1")
    monkeypatch.setattr(runtime, "parse_document", fake_parse_document)
    app = AppTest.from_file(APP_PATH).run()
    app = _select_engine(app, "Cloud AI ADE")
    app.file_uploader[0].set_value([("invoice.png", _png(), "image/png")]).run()
    next(button for button in app.button if button.label == "Parse files").click().run(timeout=20)

    assert any(metric.label == "Pages" and metric.value == "1" for metric in app.metric)
    assert any(
        metric.label == "Estimated cost" and metric.value == "$1.3550" for metric in app.metric
    )
    assert any("1,000,000 input tokens" in caption.value for caption in app.caption)
    assert any("Invoice total: 42" in item.value for item in app.markdown)
    assert [tab.label for tab in app.tabs] == [
        "Input preview",
        "Output",
        "Annotated PDF",
        "Markdown",
        "HTML",
        "JSON",
    ]
    assert {button.label for button in app.download_button} == {
        "Download Markdown",
        "Download HTML",
        "Download annotated PDF",
        "Download Paperplane JSON",
        "Download ADE v2 JSON",
        "Download batch ZIP",
    }
    progress = app.get("progress")
    assert len(progress) == 1
    assert progress[0].proto.value == 100
    assert "100%" in progress[0].proto.text
    assert not any("Private local workspace" in str(element.value) for element in app.get("badge"))

    app.session_state["workspace_view"] = "Annotated PDF"
    app.run()
    assert any("grounded blocks" in caption.value for caption in app.caption)

    app.session_state["workspace_view"] = "Markdown"
    app.run()
    assert any("Invoice total: 42" in code.value for code in app.code)

    app.session_state["workspace_view"] = "HTML"
    app.run()
    assert any("Sanitized standalone HTML" in caption.value for caption in app.caption)
    assert any("paperplane-html-page" in item.proto.body for item in app.get("html"))

    app.session_state["workspace_view"] = "JSON"
    app.run()
    assert app.json


def test_failed_batch_still_reaches_full_progress(monkeypatch) -> None:
    async def fake_parse_document(**_kwargs):
        raise ValueError("Unreadable document")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runtime, "parse_document", fake_parse_document)
    app = AppTest.from_file(APP_PATH).run()
    app = _select_engine(app, "Cloud AI ADE")
    app.file_uploader[0].set_value([("broken.png", _png(), "image/png")]).run()
    next(button for button in app.button if button.label == "Parse files").click().run(timeout=20)

    progress = app.get("progress")
    assert progress[0].proto.value == 100
    assert progress[0].proto.text == "Batch complete — 100%"
    assert any("Unreadable document" in error.value for error in app.error)


def test_app_allows_private_agnes_visual_parse(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test")
    app = AppTest.from_file(APP_PATH).run()
    app = _select_engine(app, "Cloud AI ADE")
    app.selectbox[0].select("Agnes 2.5 Flash").run()
    app.file_uploader[0].set_value([("invoice.png", _png(), "image/png")]).run()

    assert not app.error
    assert not next(button for button in app.button if button.label == "Parse files").disabled


def test_app_lists_only_supported_document_models(monkeypatch) -> None:
    _clear_api_keys(monkeypatch)
    app = AppTest.from_file(APP_PATH).run()
    app = _select_engine(app, "Cloud AI ADE")

    assert app.selectbox[0].options == [
        "Grok 4.6",
        "GPT-5.6 Luna",
        "Gemini 3.5 Flash-Lite",
        "Gemini 3.7 Flash",
        "Claude Sonnet 5",
        "Agnes 2.5 Flash",
    ]


def test_app_accepts_legacy_gemini_key_as_fallback(monkeypatch) -> None:
    _clear_api_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-test")
    app = AppTest.from_file(APP_PATH).run()
    app = _select_engine(app, "Cloud AI ADE")
    app.selectbox[0].select("Gemini 3.7 Flash").run()
    app.file_uploader[0].set_value([("invoice.png", _png(), "image/png")]).run()

    assert not next(button for button in app.button if button.label == "Parse files").disabled
    assert not any("GOOGLE_API_KEY" in warning.value for warning in app.warning)


def test_google_key_takes_precedence_over_legacy_gemini_key(monkeypatch) -> None:
    observed: dict[str, str] = {}

    async def fake_parse_document(**kwargs):
        observed["api_key"] = kwargs["api_key"]
        return assemble_parse_response(
            document_id="document",
            job_id="request",
            model=kwargs["model"],
            ai_model=kwargs["ai_model"],
            processing_strategy="ai",
            source_page_count=1,
            page_range=(1, 1),
            pages=[AgenticPageInput(page_number=1)],
        )

    _clear_api_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test")
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-test")
    monkeypatch.setattr(runtime, "parse_document", fake_parse_document)
    app = AppTest.from_file(APP_PATH).run()
    app = _select_engine(app, "Cloud AI ADE")
    app.selectbox[0].select("Gemini 3.7 Flash").run()
    app.file_uploader[0].set_value([("invoice.png", _png(), "image/png")]).run()
    next(button for button in app.button if button.label == "Parse files").click().run(timeout=20)

    assert observed["api_key"] == "google-test"


def test_app_exposes_four_exclusive_engines_and_per_file_ranges(monkeypatch) -> None:
    _clear_api_keys(monkeypatch)
    app = AppTest.from_file(APP_PATH).run()

    assert [item.label for item in list(app.toggle)[:4]] == [
        "Docling ADE",
        "PDF Inspector ADE",
        "Cloud AI ADE",
        "Ollama ADE",
    ]
    assert [item.label for item in list(app.sidebar.toggle)[:4]] == [
        "Docling ADE",
        "PDF Inspector ADE",
        "Cloud AI ADE",
        "Ollama ADE",
    ]
    assert len(app.sidebar.file_uploader) == 1
    app = _select_engine(app, "Docling ADE")
    app.file_uploader[0].set_value(
        [("first.png", _png(), "image/png"), ("second.png", _png(), "image/png")]
    ).run()

    assert [item.label for item in app.number_input] == [
        "Start page — first.png",
        "End page — first.png",
        "Start page — second.png",
        "End page — second.png",
    ]


def test_engine_toggles_are_exclusive_and_can_all_be_off(monkeypatch) -> None:
    _clear_api_keys(monkeypatch)
    app = AppTest.from_file(APP_PATH).run()

    app = _select_engine(app, "Docling ADE")
    app = _select_engine(app, "PDF Inspector ADE")
    values = {item.label: item.value for item in list(app.toggle)[:4]}
    assert values == {
        "Docling ADE": False,
        "PDF Inspector ADE": True,
        "Cloud AI ADE": False,
        "Ollama ADE": False,
    }

    app = (
        next(item for item in app.toggle if item.label == "PDF Inspector ADE")
        .set_value(False)
        .run()
    )
    assert not any(item.value for item in list(app.toggle)[:4])


def test_app_rejects_non_pdf_batch_for_pdf_inspector(monkeypatch) -> None:
    _clear_api_keys(monkeypatch)
    app = AppTest.from_file(APP_PATH).run()
    app = _select_engine(app, "PDF Inspector ADE")
    app.file_uploader[0].set_value([("invoice.png", _png(), "image/png")]).run()

    assert any("PDF files only" in error.value for error in app.error)
    assert next(button for button in app.button if button.label == "Parse files").disabled
