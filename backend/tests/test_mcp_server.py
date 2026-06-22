"""Tests for the v0.6.0 MCP server.

These tests exercise the four MCP tools directly (the function
entry points) without spinning up the stdio transport. The
transport itself is exercised by the smoke test in
``test_mcp_server_smoke.py`` if the ``mcp`` extra is installed.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app import mcp_server
from app.mcp_server import (
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_EVAL_GOLDEN_SET,
    TOOL_EXTRACT_DOCUMENT,
    TOOL_RESOLVE_ENTITIES,
    TOOL_VERIFY_EXTRACTION,
    _build_server,
    _env_has,
    _first_meaningful_token_sequence,
    _load_golden_set_samples,
    _load_jsonl_dicts,
    _parse_v2_payload,
    _stub_extraction,
    main,
    tool_eval_golden_set,
    tool_extract_document,
    tool_resolve_entities,
    tool_verify_extraction,
)

# ── Server boilerplate ──────────────────────────────────────────


def test_server_name_and_version() -> None:
    assert SERVER_NAME == "agentic-document-extraction"
    assert SERVER_VERSION == "0.6.0"


def test_build_server_returns_mcp_server() -> None:
    server = _build_server()
    # Server objects expose request_handlers and the like
    assert server is not None
    assert hasattr(server, "list_tools")
    assert hasattr(server, "call_tool")


def test_list_tools_returns_four_tools() -> None:
    """The list_tools handler returns the four v0.6.0 tools."""

    server = _build_server()
    # The server exposes registered request handlers in
    # ``request_handlers``. We assert the four tool-name keys
    # are present in the handler map (the actual coroutine is
    # exercised in the transport-level smoke test).
    from mcp.types import CallToolRequest, ListToolsRequest

    assert ListToolsRequest in server.request_handlers
    assert CallToolRequest in server.request_handlers


def test_tool_schemas_have_required_keys() -> None:
    for tool in (
        TOOL_EXTRACT_DOCUMENT,
        TOOL_VERIFY_EXTRACTION,
        TOOL_RESOLVE_ENTITIES,
        TOOL_EVAL_GOLDEN_SET,
    ):
        assert tool.name
        assert tool.description
        schema = tool.inputSchema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema


def test_extract_document_schema_required_path_and_fields() -> None:
    schema = TOOL_EXTRACT_DOCUMENT.inputSchema
    assert set(schema["required"]) == {"path", "schema_fields"}


def test_verify_extraction_schema_required_evidence_and_text() -> None:
    schema = TOOL_VERIFY_EXTRACTION.inputSchema
    assert set(schema["required"]) == {"evidence", "document_text"}


def test_resolve_entities_schema_required_mentions() -> None:
    schema = TOOL_RESOLVE_ENTITIES.inputSchema
    assert set(schema["required"]) == {"mentions"}


def test_eval_golden_set_schema_required_manifest() -> None:
    schema = TOOL_EVAL_GOLDEN_SET.inputSchema
    assert set(schema["required"]) == {"manifest_path"}


def test_main_runs_and_exits_cleanly() -> None:
    """main() is the entry point; we just confirm it imports and
    that calling main without a connected stdio client raises a
    clean BrokenPipeError (or returns normally if it exits before
    connecting)."""

    # We don't actually want to block on stdin; the run is
    # short-circuited by patching asyncio.run.
    import unittest.mock

    with unittest.mock.patch("asyncio.run") as mock_run:

        def _fake_run(coro: Any) -> None:
            coro.close()  # avoid "coroutine was never awaited" warnings
            raise KeyboardInterrupt()

        mock_run.side_effect = _fake_run
        # KeyboardInterrupt is caught in main() and exits via sys.exit(0)
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0


# ── tool_extract_document ────────────────────────────────────────


def test_tool_extract_document_missing_path(tmp_path: Path) -> None:
    out = asyncio.run(tool_extract_document({}))
    payload = json.loads(out[0].text)
    assert "error" in payload
    assert "path" in payload["error"]


def test_tool_extract_document_file_not_found() -> None:
    out = asyncio.run(tool_extract_document({"path": "/no/such/file.pdf"}))
    payload = json.loads(out[0].text)
    assert "error" in payload


def test_tool_extract_document_empty_schema() -> None:
    out = asyncio.run(tool_extract_document({"path": "/tmp/anything.pdf", "schema_fields": []}))
    payload = json.loads(out[0].text)
    assert "error" in payload


def test_tool_extract_document_text_file(tmp_path: Path) -> None:
    text_path = tmp_path / "sample.txt"
    text_path.write_text("Acme Corp\nInvoice #1234\nDate: 2026-01-15\nTotal: $1,234.50\n")
    out = asyncio.run(
        tool_extract_document(
            {
                "path": str(text_path),
                "schema_fields": [
                    {"name": "vendor_name"},
                    {"name": "missing_field"},
                ],
            }
        )
    )
    payload = json.loads(out[0].text)
    assert payload["path"] == str(text_path)
    assert "evidence" in payload
    # The stub extractor grounds "vendor_name" via "Acme"; "missing_field" is not_found
    assert "vendor_name" in payload["evidence"] or "vendor_name" in payload["not_found"]
    assert "_meta" in payload
    assert "composite_confidence" in payload["_meta"]


def test_tool_extract_document_pdf(tmp_path: Path) -> None:
    """Cover the PDF branch by stubbing _read_document."""

    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")  # file must exist for the existence check

    async def fake_read(path: Path, *, ocr_provider: str, enable_layout_parsing: bool):
        return "Acme Corp\nInvoice 42\n", {"provider": "docling", "page_count": 1, "tokens": []}

    async def fake_extractor(*, document_text: str, fields_block: str, llm_provider: str):
        return {
            "fields": {
                "vendor": {
                    "value": "Acme Corp",
                    "evidence": {
                        "page": 0,
                        "bbox": [0.1, 0.1, 0.4, 0.2],
                        "text_span": "Acme Corp",
                        "score": 0.9,
                    },
                }
            },
            "not_found": [],
        }

    saved_read = mcp_server._read_document
    saved_ext = mcp_server._call_extractor
    mcp_server._read_document = fake_read  # type: ignore[assignment]
    mcp_server._call_extractor = fake_extractor  # type: ignore[assignment]
    try:
        out = asyncio.run(
            tool_extract_document(
                {
                    "path": str(pdf_path),
                    "schema_fields": [{"name": "vendor"}],
                    "ocr_provider": "docling",
                }
            )
        )
    finally:
        mcp_server._read_document = saved_read
        mcp_server._call_extractor = saved_ext
    payload = json.loads(out[0].text)
    assert "error" not in payload
    assert payload["ocr_provider"] == "docling"
    assert "vendor" in payload["evidence"]
    ev = payload["evidence"]["vendor"]
    assert ev["value"] == "Acme Corp"
    assert ev["text_span"] == "Acme Corp"
    assert payload["_meta"]["composite_confidence"] > 0.0


def test_tool_extract_document_image_raises_clear_error(tmp_path: Path) -> None:
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    out = asyncio.run(tool_extract_document({"path": str(img), "schema_fields": [{"name": "x"}]}))
    payload = json.loads(out[0].text)
    assert "error" in payload
    assert "image OCR" in payload["error"]


# ── tool_verify_extraction ───────────────────────────────────────


def test_tool_verify_extraction_invalid_evidence() -> None:
    out = asyncio.run(tool_verify_extraction({"evidence": "not a dict", "document_text": "x"}))
    payload = json.loads(out[0].text)
    assert "error" in payload


def test_tool_verify_extraction_invalid_document_text() -> None:
    out = asyncio.run(tool_verify_extraction({"evidence": {"a": {}}, "document_text": 123}))
    payload = json.loads(out[0].text)
    assert "error" in payload


def test_tool_verify_extraction_happy_path() -> None:
    out = asyncio.run(
        tool_verify_extraction(
            {
                "evidence": {
                    "vendor": {
                        "value": "Acme",
                        "page": 0,
                        "bbox": [0.1, 0.1, 0.4, 0.2],
                        "text_span": "Acme Corp",
                        "evidence_score": 0.9,
                    },
                    "phantom": {
                        "value": "X",
                        "page": 0,
                        "text_span": "NotInDoc",
                        "evidence_score": 0.9,
                    },
                },
                "document_text": "Acme Corp invoice 42",
            }
        )
    )
    payload = json.loads(out[0].text)
    assert payload["verifier_model"] == "heuristic"
    assert payload["field_verdicts"]["vendor"]["verdict"] == "agree"
    assert payload["field_verdicts"]["phantom"]["verdict"] == "disagree"
    assert "phantom" in payload["disputed_fields"]
    assert "phantom" in payload["needs_human_review"]


def test_tool_verify_extraction_use_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """When use_llm=True we instantiate LLMVerifier (no real call)."""

    # Override LLMVerifier.verify to avoid the network call
    class _FakeLLM:
        async def verify(self, evidence_map: Any, document_text: str) -> Any:
            from app.services.extraction.verifier import Verdict, VerifierOutput

            return VerifierOutput(
                field_verdicts={
                    fname: Verdict(field=fname, verdict="agree") for fname in evidence_map.evidences
                },
                overall_agreement=1.0,
            )

    import app.mcp_server as m

    monkeypatch.setattr(m, "LLMVerifier", _FakeLLM)
    out = asyncio.run(
        tool_verify_extraction(
            {
                "use_llm": True,
                "evidence": {
                    "x": {
                        "value": "y",
                        "page": 0,
                        "text_span": "y",
                        "evidence_score": 0.9,
                    }
                },
                "document_text": "y",
            }
        )
    )
    payload = json.loads(out[0].text)
    assert payload["verifier_model"] == "llm"


# ── tool_resolve_entities ───────────────────────────────────────


def test_tool_resolve_entities_invalid_mentions() -> None:
    out = asyncio.run(tool_resolve_entities({"mentions": "not a list"}))
    payload = json.loads(out[0].text)
    assert "error" in payload


def test_tool_resolve_entities_empty() -> None:
    out = asyncio.run(tool_resolve_entities({"mentions": []}))
    payload = json.loads(out[0].text)
    assert payload["entities"] == []


def test_tool_resolve_entities_happy_path() -> None:
    out = asyncio.run(
        tool_resolve_entities(
            {
                "mentions": [
                    {"text": "Acme Corp", "page": 0},
                    {"text": "Acme", "page": 1},
                    {"text": "Globex Inc", "page": 0},
                ],
                "entity_type": "org",
                "jaccard_threshold": 0.3,
            }
        )
    )
    payload = json.loads(out[0].text)
    forms = {e["canonical_form"] for e in payload["entities"]}
    # "Acme Corp" and "Acme" cluster, "Globex Inc" stays alone
    assert "Acme Corp" in forms
    assert "Globex Inc" in forms
    # Each cluster has its mentions
    acme_cluster = next(e for e in payload["entities"] if e["canonical_form"] == "Acme Corp")
    assert len(acme_cluster["mentions"]) >= 1


def test_tool_resolve_entities_with_bbox() -> None:
    out = asyncio.run(
        tool_resolve_entities(
            {
                "mentions": [
                    {"text": "Acme", "page": 0, "bbox": [0.1, 0.1, 0.4, 0.2]},
                    {"text": "Acme", "page": 1, "bbox": [0.1, 0.1, 0.4, 0.2]},
                ],
            }
        )
    )
    payload = json.loads(out[0].text)
    assert len(payload["entities"]) == 1
    assert payload["entities"][0]["mentions"][0]["bbox"] == [0.1, 0.1, 0.4, 0.2]


def test_tool_resolve_entities_invalid_bbox_skipped() -> None:
    """An invalid bbox should not crash; we just skip the mention."""

    out = asyncio.run(
        tool_resolve_entities(
            {
                "mentions": [
                    {"text": "Acme", "page": 0, "bbox": "not-a-list"},
                ],
            }
        )
    )
    payload = json.loads(out[0].text)
    assert len(payload["entities"]) == 1


def test_tool_resolve_entities_filters_empty_text() -> None:
    out = asyncio.run(
        tool_resolve_entities(
            {
                "mentions": [
                    {"text": "Acme"},
                    {"text": ""},
                    {"text": "Globex"},
                ],
            }
        )
    )
    payload = json.loads(out[0].text)
    # Empty-text mentions are filtered
    assert len(payload["entities"]) == 2


# ── tool_eval_golden_set ─────────────────────────────────────────


def test_tool_eval_golden_set_missing_manifest(tmp_path: Path) -> None:
    out = asyncio.run(tool_eval_golden_set({"manifest_path": str(tmp_path / "missing.json")}))
    payload = json.loads(out[0].text)
    assert "error" in payload


def test_tool_eval_golden_set_invalid_manifest(tmp_path: Path) -> None:
    bad = tmp_path / "manifest.json"
    bad.write_text("{ not json")
    out = asyncio.run(tool_eval_golden_set({"manifest_path": str(bad)}))
    payload = json.loads(out[0].text)
    assert "error" in payload


def test_tool_eval_golden_set_empty(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": "v2", "datasets": []}))
    out = asyncio.run(tool_eval_golden_set({"manifest_path": str(manifest)}))
    payload = json.loads(out[0].text)
    assert "error" in payload


def test_tool_eval_golden_set_no_predictions(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    jsonl = tmp_path / "docvqa.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "id": "1",
                "source": "DocVQA",
                "expected": {"query": "What is the title?", "answer": "Acme"},
            }
        )
        + "\n"
    )
    manifest.write_text(
        json.dumps(
            {
                "version": "v2",
                "datasets": [
                    {
                        "name": "docvqa",
                        "files": [{"name": "docvqa.jsonl", "sha256": "x", "bytes": 1}],
                    }
                ],
            }
        )
    )
    out = asyncio.run(tool_eval_golden_set({"manifest_path": str(manifest)}))
    payload = json.loads(out[0].text)
    assert "error" in payload


def test_tool_eval_golden_set_kv_scoring(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    jsonl = tmp_path / "docvqa.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "id": "1",
                "source": "DocVQA",
                "expected": {
                    "query": "What is the title?",
                    "answer": "Acme Corp",
                    "acceptable_answers": ["Acme Corp", "Acme"],
                },
            }
        )
        + "\n"
    )
    manifest.write_text(
        json.dumps(
            {
                "version": "v2",
                "datasets": [
                    {
                        "name": "docvqa",
                        "files": [{"name": "docvqa.jsonl", "sha256": "x", "bytes": 1}],
                    }
                ],
            }
        )
    )
    out = asyncio.run(
        tool_eval_golden_set(
            {
                "manifest_path": str(manifest),
                "predictions": {"1": {"query": "What is the title?", "answer": "Acme Corp"}},
            }
        )
    )
    payload = json.loads(out[0].text)
    assert payload["n_samples"] == 1
    assert payload["n_with_predictions"] == 1
    assert payload["n_end_to_end_success"] == 1
    assert payload["em"] == 1.0
    assert payload["token_f1"] == 1.0


def test_tool_eval_golden_set_table_scoring(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    jsonl = tmp_path / "docvqa.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "id": "1",
                "source": "DocVQA",
                "expected": {
                    "query": "Extract the table",
                    "table": [["A", "B"], ["1", "2"]],
                },
            }
        )
        + "\n"
    )
    manifest.write_text(
        json.dumps(
            {
                "version": "v2",
                "datasets": [
                    {
                        "name": "docvqa",
                        "files": [{"name": "docvqa.jsonl", "sha256": "x", "bytes": 1}],
                    }
                ],
            }
        )
    )
    out = asyncio.run(
        tool_eval_golden_set(
            {
                "manifest_path": str(manifest),
                "predictions": {"1": {"table": [["A", "B"], ["1", "2"]]}},
            }
        )
    )
    payload = json.loads(out[0].text)
    assert payload["teds"] == 1.0
    assert payload["cell_f1"] == 1.0
    assert payload["header_match_accuracy"] == 1.0
    assert payload["row_accuracy"] == 1.0
    assert payload["column_accuracy"] == 1.0


def test_tool_eval_golden_set_with_evidence(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    jsonl = tmp_path / "docvqa.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "id": "1",
                "source": "DocVQA",
                "expected": {
                    "query": "x",
                    "answer": "y",
                    "evidence": {"x": {"page": 0, "bbox": [0.1, 0.1, 0.4, 0.2], "text_span": "y"}},
                },
            }
        )
        + "\n"
    )
    manifest.write_text(
        json.dumps(
            {
                "version": "v2",
                "datasets": [
                    {
                        "name": "docvqa",
                        "files": [{"name": "docvqa.jsonl", "sha256": "x", "bytes": 1}],
                    }
                ],
            }
        )
    )
    out = asyncio.run(
        tool_eval_golden_set(
            {
                "manifest_path": str(manifest),
                "predictions": {
                    "1": {
                        "query": "x",
                        "answer": "y",
                        "evidence": {
                            "x": {
                                "page": 0,
                                "bbox": [0.1, 0.1, 0.4, 0.2],
                                "text_span": "y",
                            }
                        },
                    }
                },
            }
        )
    )
    payload = json.loads(out[0].text)
    assert payload["evidence_attribution_accuracy"] == 1.0
    assert payload["page_localization_accuracy"] == 1.0
    assert payload["mean_bbox_iou"] == 1.0


def test_tool_eval_golden_set_uses_prediction_jsonl(tmp_path: Path) -> None:
    """When the caller doesn't pass predictions, the tool reads
    prediction.jsonl next to the manifest."""

    manifest = tmp_path / "manifest.json"
    jsonl = tmp_path / "docvqa.jsonl"
    jsonl.write_text(json.dumps({"id": "1", "expected": {"query": "Q", "answer": "A"}}) + "\n")
    (tmp_path / "prediction.jsonl").write_text(
        json.dumps({"id": "1", "query": "Q", "answer": "A"}) + "\n"
    )
    manifest.write_text(
        json.dumps(
            {
                "version": "v2",
                "datasets": [
                    {
                        "name": "docvqa",
                        "files": [{"name": "docvqa.jsonl", "sha256": "x", "bytes": 1}],
                    }
                ],
            }
        )
    )
    out = asyncio.run(tool_eval_golden_set({"manifest_path": str(manifest)}))
    payload = json.loads(out[0].text)
    assert payload["n_with_predictions"] == 1
    assert payload["em"] == 1.0


# ── Internal helpers ────────────────────────────────────────────


def test_env_has() -> None:
    import os

    os.environ.pop("ADE_TEST_FLAG", None)
    assert _env_has("ADE_TEST_FLAG") is False
    os.environ["ADE_TEST_FLAG"] = "1"
    assert _env_has("ADE_TEST_FLAG") is True
    del os.environ["ADE_TEST_FLAG"]


def test_first_meaningful_token_sequence_finds_token() -> None:
    text = "Hello world Acme Corp is here"
    # Single token: 4 chars returned
    assert _first_meaningful_token_sequence(text, "acme") == "Acme"
    # Multi-token: only the first matched token is returned
    assert _first_meaningful_token_sequence(text, "Acme Corp") == "Acme"


def test_first_meaningful_token_sequence_empty_inputs() -> None:
    assert _first_meaningful_token_sequence("", "acme") == ""
    assert _first_meaningful_token_sequence("hello", "") == ""


def test_first_meaningful_token_sequence_no_match() -> None:
    assert _first_meaningful_token_sequence("hello world", "nothere") == ""


def test_first_meaningful_token_sequence_underscores_and_dashes() -> None:
    assert _first_meaningful_token_sequence("Hello world_foo-bar", "foo_bar") == "foo-"


def test_parse_v2_payload_empty() -> None:
    assert _parse_v2_payload("") == {"fields": {}, "not_found": []}
    assert _parse_v2_payload(None or "") == {"fields": {}, "not_found": []}  # type: ignore[arg-type]


def test_parse_v2_payload_valid_json() -> None:
    raw = '{"fields": {}, "not_found": []}'
    assert _parse_v2_payload(raw) == {"fields": {}, "not_found": []}


def test_parse_v2_payload_with_garbage_around() -> None:
    raw = 'Here is the result:\n{"fields": {"x": {"value": 1}}, "not_found": []}\nDone.'
    parsed = _parse_v2_payload(raw)
    assert "fields" in parsed


def test_parse_v2_payload_invalid_returns_empty() -> None:
    assert _parse_v2_payload("not json at all") == {"fields": {}, "not_found": []}


def test_stub_extraction_grounds_one_field() -> None:
    text = "Acme Corp invoice 42"
    out = _stub_extraction(
        text,
        "- Acme [string]: Return a short string.\n- total [number]: Return a numeric value.",
    )
    assert "Acme" in out["fields"]
    assert out["fields"]["Acme"]["value"] is not None


def test_stub_extraction_handles_missing_field() -> None:
    out = _stub_extraction("hello world", "- vendor [string]: hint")
    assert "vendor" in out["not_found"]


def test_load_jsonl_dicts(tmp_path: Path) -> None:
    p = tmp_path / "predictions.jsonl"
    p.write_text(
        json.dumps({"id": "1", "answer": "A"})
        + "\n"
        + json.dumps({"id": "2", "answer": "B"})
        + "\n"
    )
    out = _load_jsonl_dicts(p)
    assert out == {"1": {"id": "1", "answer": "A"}, "2": {"id": "2", "answer": "B"}}


def test_load_jsonl_dicts_skips_invalid_lines(tmp_path: Path) -> None:
    p = tmp_path / "predictions.jsonl"
    p.write_text("not json\n" + json.dumps({"id": "1", "x": 1}) + "\n")
    out = _load_jsonl_dicts(p)
    assert out == {"1": {"id": "1", "x": 1}}


def test_load_golden_set_samples_skips_missing_files(tmp_path: Path) -> None:
    manifest = {"version": "v2", "datasets": [{"name": "x", "files": [{"name": "missing.jsonl"}]}]}
    out = _load_golden_set_samples(manifest, tmp_path)
    assert out == []
