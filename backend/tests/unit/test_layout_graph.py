import shutil
import uuid
from pathlib import Path

import fitz
import pytest
from PIL import Image

from app.models.enums import ArtifactType
from app.models.schemas import ParseSettings
from app.services.extraction.graph import ParserState, build_parser_graph, reflection_router
from app.services.parsing.agentic_contracts import QualityScore
from app.services.parsing.contracts import BoundingBox, RecognitionCandidate, Region
from app.services.parsing.parser import LayoutParser
from app.services.parsing.review import RegionReview, ReviewResult


def test_public_contract_uses_document_input_mode_and_context_artifact() -> None:
    assert ParseSettings().input_mode == "mixed"
    assert ParseSettings(input_mode="scanned").input_mode == "scanned"
    assert ArtifactType.CONTEXT_JSON == "context_json"
    with pytest.raises(ValueError):
        ParseSettings(input_mode="auto")


def test_graph_has_document_pipeline_and_repair_edge() -> None:
    graph = build_parser_graph(LayoutParser()).get_graph()
    names = set(graph.nodes)
    assert {
        "ingest_and_render",
        "visual_segmentation",
        "local_recognition",
        "layout_stitching",
        "cloud_context_review",
        "finalize",
    } <= names
    assert ("cloud_context_review", "local_recognition") in {
        (edge.source, edge.target) for edge in graph.edges
    }


def test_reflection_router_is_bounded_to_two_repairs() -> None:
    base: ParserState = {"needs_repair": True, "repair_count": 1, "max_repairs": 2}
    assert reflection_router(base) == "local_recognition"
    assert reflection_router({**base, "repair_count": 2}) == "finalize"
    assert reflection_router({**base, "needs_repair": False}) == "finalize"


def test_reflection_router_honors_zero_repairs() -> None:
    assert (
        reflection_router({"needs_repair": True, "repair_count": 0, "max_repairs": 0}) == "finalize"
    )


def test_stitching_orders_columns_and_builds_grounded_context() -> None:
    parser = LayoutParser()
    zones = [
        Region(
            type="text",
            bbox=BoundingBox(left=0.55, top=0.1, right=0.95, bottom=0.2),
            content="Right",
            source="native",
        ),
        Region(
            type="heading",
            bbox=BoundingBox(left=0.05, top=0.02, right=0.95, bottom=0.08),
            content="Title",
            source="native",
        ),
        Region(
            type="text",
            bbox=BoundingBox(left=0.05, top=0.1, right=0.45, bottom=0.2),
            content="Left",
            source="native",
        ),
    ]

    result = parser.stitch_document({1: zones})

    assert result.clean_markdown.index("# Title") < result.clean_markdown.index("Left")
    assert result.clean_markdown.index("Left") < result.clean_markdown.index("Right")
    assert len(result.context_chunks) == 3
    assert result.context_chunks[0].id == "p0001-r0001"
    assert "<!-- p:1 bbox:" in result.grounded_markdown


def test_checkpoint_state_contains_paths_not_image_bytes() -> None:
    state: ParserState = {
        "job_id": "job",
        "source_path": str(Path("source.pdf")),
        "page_images": ["work/page-0001.png"],
    }
    assert all(isinstance(item, str) for item in state["page_images"])


@pytest.mark.asyncio
async def test_native_graph_produces_all_llm_ready_outputs() -> None:
    tmp_path = Path("backend/tests/_test_uploads") / f"graph-{uuid.uuid4().hex}"
    tmp_path.mkdir(parents=True)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Native document text")
    source = tmp_path / "native.pdf"
    source.write_bytes(document.tobytes())
    document.close()

    try:
        result = await build_parser_graph(LayoutParser()).ainvoke(
            {
                "job_id": "native-job",
                "source_path": str(source),
                "work_dir": str(tmp_path / "runtime"),
                "settings": ParseSettings(input_mode="native").model_dump(mode="json"),
                "repair_count": 0,
                "warnings": [],
            }
        )

        assert "Native document text" in result["markdown"]
        assert result["context"]["chunks"][0]["page"] == 1
        assert "bbox:" in result["grounded_markdown"]
        assert result["status"] == "completed"
    finally:
        shutil.rmtree(tmp_path)


@pytest.mark.asyncio
async def test_visual_review_routes_one_repair_then_accepts() -> None:
    class Reviewer:
        calls = 0

        async def review(
            self,
            image_png,
            markdown,
            allowed_region_ids,
            candidate_context=None,
            coordinate_manifest=None,
        ):
            self.calls += 1
            verdict = "fail" if self.calls == 1 else "pass"
            score = QualityScore(
                extraction_accuracy=0.8,
                structural_fidelity=0.8,
                completeness=0.8,
                markdown_consistency=0.8,
                overall=0.8,
            )
            return ReviewResult(
                score=score,
                regions=[
                    RegionReview(
                        region_id=allowed_region_ids[0],
                        verdict=verdict,
                        reason="alignment check",
                        repair_hint="re-read" if verdict == "fail" else None,
                    )
                ],
            )

    reviewer = Reviewer()
    tmp_path = Path("backend/tests/_test_uploads") / f"review-{uuid.uuid4().hex}"
    tmp_path.mkdir(parents=True)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Review me")
    source = tmp_path / "native.pdf"
    source.write_bytes(document.tobytes())
    document.close()
    try:
        result = await build_parser_graph(LayoutParser(), reviewer=reviewer).ainvoke(
            {
                "job_id": "review-job",
                "source_path": str(source),
                "work_dir": str(tmp_path / "runtime"),
                "settings": ParseSettings(
                    input_mode="native",
                    cloud_mode="all_pages",
                    review_model="review-model",
                    blind_local_retry=True,
                ).model_dump(mode="json"),
                "repair_count": 0,
                "max_repairs": 1,
                "warnings": [],
            }
        )
    finally:
        shutil.rmtree(tmp_path)

    assert reviewer.calls == 2
    assert result["repair_count"] == 1
    assert result["reviews"][1]["quality_status"] == "pass"


@pytest.mark.asyncio
async def test_adaptive_cloud_review_skips_clean_pages() -> None:
    class Reviewer:
        calls = 0

        async def review(
            self,
            image_png,
            markdown,
            allowed_region_ids,
            candidate_context=None,
            coordinate_manifest=None,
        ):
            self.calls += 1
            raise AssertionError("clean adaptive pages must not call the cloud reviewer")

    reviewer = Reviewer()
    tmp_path = Path("backend/tests/_test_uploads") / f"adaptive-{uuid.uuid4().hex}"
    tmp_path.mkdir(parents=True)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Clean native page")
    source = tmp_path / "native.pdf"
    source.write_bytes(document.tobytes())
    document.close()
    try:
        result = await build_parser_graph(LayoutParser(), reviewer=reviewer).ainvoke(
            {
                "job_id": "adaptive-job",
                "source_path": str(source),
                "work_dir": str(tmp_path / "runtime"),
                "settings": ParseSettings(
                    input_mode="native",
                    cloud_mode="adaptive",
                    review_model="review-model",
                ).model_dump(mode="json"),
                "repair_count": 0,
                "warnings": [],
            }
        )
    finally:
        shutil.rmtree(tmp_path)

    assert reviewer.calls == 0
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_mixed_image_page_runs_full_local_recognition(tmp_path) -> None:
    class LayoutEngine:
        async def segment_document(self, **kwargs):
            return {
                page: [
                    Region(
                        type="text",
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.3),
                        content="Paddle text",
                        source="paddleocr_vl",
                    )
                ]
                for page in kwargs["page_numbers"]
            }

    class LocalEngine:
        calls = 0

        async def process(
            self,
            image_path,
            zone,
            device="auto",
            model=None,
            provider="ollama",
            repair_hint=None,
        ):
            self.calls += 1
            return zone.model_copy(update={"content": "GLM text", "source": "glm_ocr"})

    source = tmp_path / "scan.png"
    Image.new("RGB", (200, 100), "white").save(source)
    local = LocalEngine()
    parser = LayoutParser(
        layout_engine=LayoutEngine(),  # type: ignore[arg-type]
        text_engine=local,
        table_engine=local,
    )

    result = await build_parser_graph(parser).ainvoke(
        {
            "job_id": "mixed-scan-job",
            "source_path": str(source),
            "work_dir": str(tmp_path / "runtime"),
            "settings": ParseSettings(
                input_mode="mixed", ocr_model="glm-ocr:latest"
            ).model_dump(mode="json"),
            "repair_count": 0,
            "warnings": [],
        }
    )

    assert local.calls == 1
    assert "GLM text" in result["markdown"]
    assert result["repair_count"] == 0


@pytest.mark.asyncio
async def test_adaptive_cloud_review_receives_flagged_local_candidates(tmp_path) -> None:
    class LayoutEngine:
        async def segment_document(self, **kwargs):
            return {
                page: [
                    Region(
                        type="text",
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.3),
                        content="GLM candidate",
                        source="glm_ocr",
                        warnings=["recognition_disagreement"],
                        recognition_candidates=[
                            RecognitionCandidate(
                                source="paddleocr_vl", content="Paddle candidate"
                            ),
                            RecognitionCandidate(
                                source="glm_ocr",
                                content="GLM candidate",
                                model="glm-ocr:latest",
                                selected=True,
                            ),
                        ],
                    )
                ]
                for page in kwargs["page_numbers"]
            }

    class Reviewer:
        calls = 0
        candidates = None

        async def review(
            self,
            image_png,
            markdown,
            allowed_region_ids,
            candidate_context=None,
            coordinate_manifest=None,
        ):
            self.calls += 1
            self.candidates = candidate_context
            score = QualityScore(
                extraction_accuracy=1,
                structural_fidelity=1,
                completeness=1,
                markdown_consistency=1,
                overall=1,
            )
            return ReviewResult(
                score=score,
                regions=[
                    RegionReview(
                        region_id=allowed_region_ids[0], verdict="pass", reason="candidate accepted"
                    )
                ],
            )

    source = tmp_path / "scan.png"
    Image.new("RGB", (200, 100), "white").save(source)
    reviewer = Reviewer()
    parser = LayoutParser(layout_engine=LayoutEngine())  # type: ignore[arg-type]

    result = await build_parser_graph(parser, reviewer=reviewer).ainvoke(
        {
            "job_id": "adaptive-candidate-job",
            "source_path": str(source),
            "work_dir": str(tmp_path / "runtime"),
            "settings": ParseSettings(
                input_mode="mixed",
                cloud_mode="adaptive",
                review_model="review-model",
            ).model_dump(mode="json"),
            "repair_count": 0,
            "warnings": [],
        }
    )

    assert reviewer.calls == 1
    assert reviewer.candidates["p0001-r0001"] == [
        "paddleocr_vl: Paddle candidate",
        "glm_ocr: GLM candidate",
    ]
    assert result["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled, expected_calls", [(False, 1), (True, 2)])
async def test_cloud_disagreement_blind_retry_never_receives_cloud_feedback(
    tmp_path, enabled, expected_calls
) -> None:
    class LayoutEngine:
        async def segment_document(self, **kwargs):
            return {
                page: [
                    Region(
                        type="text",
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.3),
                        content="Paddle text",
                        source="paddleocr_vl",
                    )
                ]
                for page in kwargs["page_numbers"]
            }

    class LocalEngine:
        def __init__(self):
            self.calls = 0
            self.hints = []

        async def process(
            self,
            image_path,
            zone,
            device="auto",
            model=None,
            provider="ollama",
            repair_hint=None,
        ):
            self.calls += 1
            self.hints.append(repair_hint)
            return zone.model_copy(
                update={"content": f"GLM attempt {self.calls}", "source": "glm_ocr"}
            )

    class Reviewer:
        async def review(
            self,
            image_png,
            markdown,
            allowed_region_ids,
            candidate_context=None,
            coordinate_manifest=None,
        ):
            score = QualityScore(
                extraction_accuracy=0.5,
                structural_fidelity=1,
                completeness=1,
                markdown_consistency=1,
                overall=0.875,
            )
            return ReviewResult(
                score=score,
                regions=[
                    RegionReview(
                        region_id=allowed_region_ids[0],
                        verdict="fail",
                        reason="text does not match the boxed visual region",
                        repair_hint="use the cloud answer SECRET-CLOUD-TEXT",
                    )
                ],
            )

    source = tmp_path / f"scan-{enabled}.png"
    Image.new("RGB", (200, 100), "white").save(source)
    local = LocalEngine()
    parser = LayoutParser(
        layout_engine=LayoutEngine(),  # type: ignore[arg-type]
        text_engine=local,
        table_engine=local,
    )
    result = await build_parser_graph(parser, reviewer=Reviewer()).ainvoke(
        {
            "job_id": f"blind-{enabled}",
            "source_path": str(source),
            "work_dir": str(tmp_path / f"runtime-{enabled}"),
            "settings": ParseSettings(
                input_mode="mixed",
                ocr_model="glm-ocr:latest",
                cloud_mode="all_pages",
                review_model="review-model",
                blind_local_retry=enabled,
            ).model_dump(mode="json"),
            "repair_count": 0,
            "max_repairs": 2,
            "warnings": [],
        }
    )

    assert local.calls == expected_calls
    assert local.hints == [None] * expected_calls
    assert "SECRET-CLOUD-TEXT" not in result["markdown"]
    assert f"GLM attempt {expected_calls}" in result["markdown"]
    assert result["status"] == "completed_with_warnings"
def test_stitching_preserves_nested_heading_hierarchy_across_pages() -> None:
    parser = LayoutParser()
    pages = {
        1: [
            Region(
                type="heading",
                heading_level=1,
                bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                content="Chapter",
            ),
            Region(
                type="heading",
                heading_level=2,
                bbox=BoundingBox(left=0.1, top=0.3, right=0.9, bottom=0.4),
                content="Section",
            ),
        ],
        2: [
            Region(
                type="text",
                bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.3),
                content="Body",
            )
        ],
    }

    result = parser.stitch_document(pages)
    body = next(chunk for chunk in result.context_chunks if chunk.text == "Body")

    assert body.heading_path == ["Chapter", "Section"]
    assert body.parent_id == "p0001-r0002"
