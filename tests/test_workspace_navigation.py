from io import BytesIO
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

import paperplane.runtime as runtime
from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    ModelTokenUsage,
    NormalizedBox,
    assemble_parse_response,
)

WORKSPACE_PATH = Path(__file__).resolve().parents[1] / "workspace_app.py"


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def test_navigation_preserves_workspace_and_new_parse_keeps_session_cost(
    monkeypatch, tmp_path: Path
) -> None:
    async def fake_parse_document(**kwargs):
        return assemble_parse_response(
            document_id="document",
            job_id="session-parse",
            model=kwargs["model"],
            ai_model=kwargs["ai_model"],
            input_tokens=100,
            output_tokens=20,
            cached_input_tokens=10,
            model_usage={
                kwargs["ai_model"]: ModelTokenUsage(
                    input_tokens=100,
                    output_tokens=20,
                    cached_input_tokens=10,
                )
            },
            processing_strategy="ai",
            source_page_count=1,
            page_range=(1, 1),
            pages=[
                AgenticPageInput(
                    page_number=1,
                    blocks=[
                        AgenticBlockInput(
                            type="text",
                            markdown="Retained output",
                            box=NormalizedBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                        )
                    ],
                )
            ],
        )

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(runtime, "parse_document", fake_parse_document)
    app = AppTest.from_file(WORKSPACE_PATH).run(timeout=20)
    next(item for item in app.toggle if item.label == "Cloud AI ADE").set_value(True).run()
    app.file_uploader[0].set_value([("keep.png", _png(), "image/png")]).run()
    next(button for button in app.button if button.label == "Parse files").click().run(timeout=20)

    app.switch_page("app_pages/organize.py").run(timeout=20)
    app.text_area[0].set_value("letter\nreport").run()
    next(button for button in app.button if button.label == "Classify pages").click().run()
    app.switch_page("app_pages/cost.py").run(timeout=20)
    assert next(item for item in app.metric if item.label == "Input tokens").value == "100"
    app.switch_page("app_pages/organize.py").run(timeout=20)
    assert app.text_area[0].value == "letter\nreport"
    assert app.session_state["classify_result"] is not None

    app.switch_page("app_pages/jobs.py").run(timeout=20)
    app.switch_page("streamlit_app.py").run(timeout=20)

    assert next(item for item in app.toggle if item.label == "Cloud AI ADE").value is True
    assert app.session_state["batch_outcomes"][0].result is not None
    assert app.session_state["retained_uploads"][0].name == "keep.png"
    assert "session-parse" in app.session_state["session_usage"]
    assert any("Retained in this browser session: keep.png" in item.value for item in app.caption)
    assert any("Retained output" in item.value for item in app.markdown)

    next(button for button in app.button if button.label == "New parse").click().run()

    assert app.session_state["batch_outcomes"] == []
    assert app.session_state["retained_uploads"] == []
    assert "session-parse" in app.session_state["session_usage"]
