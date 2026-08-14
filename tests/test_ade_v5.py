from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperplane.ade_contracts import EngineOptions, to_ade_v2_parse
from paperplane.ade_workflows import (
    ClassDefinition,
    classify_document,
    section_document,
    split_document,
)
from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    AtomicLineInput,
    NormalizedBox,
    assemble_parse_response,
)
from paperplane.jobs import JobStore


def _box() -> NormalizedBox:
    return NormalizedBox(left=0.1, top=0.2, right=0.8, bottom=0.3)


def _response():
    return assemble_parse_response(
        document_id="doc-v5",
        job_id="job-v5",
        model="paperplane-ade-v5",
        pages=[
            AgenticPageInput(
                page_number=2,
                parser="docling",
                blocks=[
                    AgenticBlockInput(
                        type="text",
                        markdown="Invoice Café\nTotal: $42.00",
                        box=_box(),
                        atomic_lines=[
                            AtomicLineInput(text="Invoice Café", box=_box()),
                            AtomicLineInput(text="Total: $42.00", box=_box()),
                        ],
                    )
                ],
            )
        ],
        source_page_count=4,
        page_range=(2, 2),
        engine="docling",
    )


def test_engine_options_are_exclusive_and_cloud_cannot_enhance() -> None:
    assert EngineOptions().selected_engine is None
    assert EngineOptions(docling=True).selected_engine == "docling"
    assert EngineOptions(docling=True, cloud_enhancement=True).uses_cloud
    with pytest.raises(ValueError, match="exactly one"):
        EngineOptions(docling=True, ollama=True)
    with pytest.raises(ValueError, match="Cloud AI"):
        EngineOptions(cloud_ai=True, cloud_enhancement=True)


def test_strict_ade_v2_parse_export_has_inline_grounding_and_zero_based_ids() -> None:
    exported = to_ade_v2_parse(_response(), model_version="paperplane-5.0.0")
    payload = exported.model_dump(mode="json", exclude_none=True)

    assert payload["structure"]["id"] == "document-0"
    page = payload["structure"]["children"][0]
    block = page["children"][0]
    assert page["id"] == "page-0"
    assert page["grounding"]["page"] == 2
    assert page["status"] == "ok"
    assert block["id"] == "text-0"
    assert block["grounding"]["box"] == {
        "xmin": 0.1,
        "ymin": 0.2,
        "xmax": 0.8,
        "ymax": 0.3,
    }
    start, end = block["grounding"]["range"].values()
    assert exported.markdown[start:end] == "Invoice Café\nTotal: $42.00"
    assert len(block["atomic_grounding"]) == 2
    assert payload["metadata"]["page_count"] == 4
    assert payload["metadata"]["range_units"] == "unicode_codepoints"


def test_classify_split_and_section_return_cited_deterministic_results() -> None:
    response = _response()
    classes = [
        ClassDefinition(name="invoice", description="Invoices and totals"),
        ClassDefinition(name="letter", description="Correspondence"),
    ]
    classification = classify_document(response, classes)
    assert classification.pages[0].label == "invoice"
    assert classification.pages[0].ranges

    sections = section_document(response)
    assert sections.sections[0].title == "Invoice Café"
    assert sections.sections[0].start_reference == "text-1"

    splits = split_document(response, classes)
    assert splits.documents[0].label == "invoice"
    assert splits.documents[0].pages == [2]


def test_job_store_persists_checkpoints_and_purges_expired_artifacts(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3", tmp_path / "artifacts", ttl_days=7)
    job = store.create_job(filename="sample.pdf", engine="docling", page_range=(1, 3))
    store.mark_running(job.id)
    checkpoint = store.save_checkpoint(job.id, page=1, payload={"markdown": "page one"})
    assert checkpoint.exists()

    reopened = JobStore(tmp_path / "jobs.sqlite3", tmp_path / "artifacts", ttl_days=7)
    assert reopened.get_job(job.id).status == "running"
    assert reopened.resume_checkpoint(job.id) == (1, {"markdown": "page one"})
    reopened.complete_job(job.id, result={"ok": True})
    assert json.loads(reopened.get_job(job.id).result_json or "{}") == {"ok": True}

    reopened.delete_job(job.id)
    assert reopened.get_job(job.id) is None
    assert not checkpoint.parent.exists()
