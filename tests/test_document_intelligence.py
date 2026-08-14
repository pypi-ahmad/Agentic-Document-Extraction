from __future__ import annotations

from paperplane.calibration import CalibrationProfile, confidence_for
from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    NormalizedBox,
    assemble_parse_response,
)
from paperplane.document_intelligence import infer_document_relations


def _response():
    return assemble_parse_response(
        document_id="doc",
        job_id="job",
        model="model",
        pages=[
            AgenticPageInput(
                page_number=2,
                blocks=[
                    AgenticBlockInput(
                        type="text",
                        markdown="Heading",
                        box=NormalizedBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                    )
                ],
            )
        ],
        source_page_count=4,
        page_range=(2, 2),
    )


def test_selection_boundary_is_explicit() -> None:
    relations = infer_document_relations(_response())
    boundary = next(item for item in relations if item["type"] == "selection_boundary")
    assert boundary["page_range"] == [2, 2]
    assert "not inspected" in boundary["warning"]


def test_arbitrary_model_confidence_is_not_presented_as_calibrated() -> None:
    profile = CalibrationProfile(
        engine="ollama",
        model="glm-ocr:latest",
        version="1",
        corpus_sha256="a" * 64,
        breakpoints=[(0.0, 0.1), (1.0, 0.9)],
    )
    calibrated = confidence_for(
        0.5, engine="ollama", model="glm-ocr:latest", version="1", profile=profile
    )
    unknown = confidence_for(
        0.5, engine="ollama", model="another-model", version="1", profile=profile
    )
    assert calibrated.calibrated == 0.5
    assert unknown.calibrated is None
    assert unknown.label == "raw (uncalibrated)"
