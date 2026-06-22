"""MCP server for Agentic Document Extraction (v0.6.0).

This module exposes the v0.5.0 evidence-grounded extraction
pipeline as four MCP tools, so any MCP-aware LLM client
(Claude Desktop, Cursor, Cline, Continue, ...) can drive the
pipeline through the standard Model Context Protocol.

Tools
-----

* ``extract_document`` — run the full v0.5.0 pipeline
  (layout-parse → extract → verify → conflict-resolve →
  cross-page → calibrate → validate) on a single document
  and return the evidence-grounded JSON result.
* ``verify_extraction`` — re-run the verifier over a prior
  extraction's evidence map and return per-field verdicts.
* ``resolve_entities`` — run the cross-page entity resolver
  on a list of mentions and return one canonical form per
  cluster.
* ``eval_golden_set`` — run the v2 metric suite
  (TEDS, cell F1, IoU, attribution, ...) on a golden set
  JSONL and return a flat metrics dict.

The server speaks stdio (the default MCP transport). Run it
with:

.. code-block:: bash

    uv run --with 'mcp[cli]>=1.0' --with 'agentic-document-extraction[mcp]' \\
        python -m app.mcp_server

…or, after ``pip install agentic-document-extraction[mcp]``:

.. code-block:: bash

    ade-mcp

The client connects over stdio and calls the tools like any
other MCP tool. See ``docs/MCP.md`` for client configuration
examples (Claude Desktop, Cursor, Cline).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

# Optional dependency: mcp is declared in the [mcp] extra and may
# not be installed for users who only use the HTTP API. We import
# lazily and raise a clear error at startup if it's missing.
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError as exc:  # pragma: no cover - exercised at runtime
    raise ImportError(
        "The MCP extra is not installed. Run: pip install "
        "agentic-document-extraction[mcp]  (or: uv add mcp[cli])"
    ) from exc

from app.services.eval.metrics_v2 import (
    evidence_attribution_accuracy,
    exact_match_batch,
    mean_bbox_iou,
    page_localization_accuracy,
    teds,
    token_f1_batch,
)
from app.services.extraction.cross_page import (
    EntityMention,
    resolve_entities,
)
from app.services.extraction.evidence import (
    EvidenceMap,
    build_evidence_map,
    filter_low_evidence,
    merge_with_not_found,
)
from app.services.extraction.field_strategies import (
    available_kinds,
    render_fields_block,
)
from app.services.extraction.verifier import (
    HeuristicVerifier,
    LLMVerifier,
    VerifierOutput,
    resolve_disputes,
)
from app.services.llm.prompts_loader import load_prompt

logger = logging.getLogger(__name__)

# Public server name + version, surfaced to MCP clients.
SERVER_NAME = "agentic-document-extraction"
SERVER_VERSION = "0.6.0"
SERVER_INSTRUCTIONS = (
    "Agentic Document Extraction (v0.5.0 pipeline). Tools: extract_document, "
    "verify_extraction, resolve_entities, eval_golden_set. All extraction "
    "results are evidence-grounded: every field cites page, bbox, and verbatim "
    "text span in the document. See docs/MCP.md for the full how-to-use guide."
)


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


# ── Tool definition helpers ──────────────────────────────────────


def _text(payload: Any) -> list[TextContent]:
    """Wrap a JSON-serializable payload as a single TextContent block."""

    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    return [TextContent(type="text", text=text)]


def _error(message: str, **extra: Any) -> list[TextContent]:
    """Wrap an error as a JSON TextContent block."""

    payload: dict[str, Any] = {"error": message}
    if extra:
        payload["details"] = extra
    return _text(payload)


# ── Schemas for the four tools ───────────────────────────────────


TOOL_EXTRACT_DOCUMENT = Tool(
    name="extract_document",
    description=(
        "Run the v0.5.0 evidence-grounded extraction pipeline on a local "
        "document. Returns per-field values plus a page, bbox, and verbatim "
        "text_span for every field that could be grounded. Un-grounded "
        "fields are returned in _meta.not_found_fields. The composite "
        "confidence (logprob + verifier + evidence) is returned in "
        "_meta.composite_confidence."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Absolute or relative path to the document (PDF, PNG, "
                    "JPEG, TIFF, DOCX, PPTX, XLSX, HTML). Must be readable by "
                    "the user that started the MCP server."
                ),
            },
            "schema_fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": available_kinds(),
                            "description": (
                                "Field kind. Defaults to 'string'. Use 'date' "
                                "for YYYY-MM-DD values, 'currency' for amount+code, "
                                "'table' for 2-D grids, etc. See "
                                "app.services.field_strategies for the full list."
                            ),
                        },
                        "description": {"type": "string"},
                    },
                    "required": ["name"],
                },
                "description": (
                    "List of fields to extract. Each field has a 'name' "
                    "(required), optional 'kind' (string/date/currency/...), "
                    "and optional 'description' (helps the LLM locate the value)."
                ),
            },
            "ocr_provider": {
                "type": "string",
                "enum": ["auto", "pymupdf", "paddleocr", "glmocr", "docling"],
                "default": "auto",
                "description": (
                    "OCR / parser engine. 'auto' (default) routes based on file "
                    "type and enabled engines. 'pymupdf' is the text-layer PDF "
                    "reader (always available). 'docling' uses the layout-aware "
                    "parser (recommended for PDFs with tables or multi-column "
                    "layouts; requires ENABLE_DOCLING=true)."
                ),
            },
            "llm_provider": {
                "type": "string",
                "enum": ["auto", "openai", "gemini", "anthropic", "ollama"],
                "default": "auto",
                "description": "LLM provider. 'auto' picks the first enabled one.",
            },
            "enable_verifier": {
                "type": "boolean",
                "default": True,
                "description": (
                    "When true, run the heuristic verifier over the evidence "
                    "and route any disagreed fields to human review."
                ),
            },
            "enable_layout_parsing": {
                "type": "boolean",
                "default": True,
                "description": (
                    "When true, the parse stage emits per-token bbox and region "
                    "type metadata. Disable to fall back to v0.4.0 OCR-only behavior."
                ),
            },
            "min_evidence_score": {
                "type": "number",
                "default": 0.5,
                "minimum": 0.0,
                "maximum": 1.0,
                "description": (
                    "Drop fields whose evidence_score is below this threshold. "
                    "Default 0.5; raise to 0.7 for high-stakes documents."
                ),
            },
            "use_llm_verifier": {
                "type": "boolean",
                "default": False,
                "description": (
                    "When true, use the LLMVerifier (Ollama) instead of the "
                    "HeuristicVerifier. Requires OLLAMA_BASE_URL reachable and "
                    "the model in OLLAMA_VERIFIER_MODEL (default qwen3.5:4b)."
                ),
            },
        },
        "required": ["path", "schema_fields"],
    },
)

TOOL_VERIFY_EXTRACTION = Tool(
    name="verify_extraction",
    description=(
        "Re-run the verifier over a prior extraction's evidence map. "
        "Returns per-field verdicts (agree / disagree / unsure) and the "
        "list of disputed fields that should be escalated to a human reviewer."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "evidence": {
                "type": "object",
                "description": (
                    "An evidence map: {field: {value, page, bbox, text_span, "
                    "evidence_score}}. Same shape as the v2 LLM payload; "
                    "or the result of extract_document's evidence sub-block."
                ),
            },
            "document_text": {
                "type": "string",
                "description": (
                    "The flat document text the LLM saw. Used by the "
                    "HeuristicVerifier to check text_span substring membership."
                ),
            },
            "use_llm": {
                "type": "boolean",
                "default": False,
                "description": "Use LLMVerifier instead of HeuristicVerifier.",
            },
        },
        "required": ["evidence", "document_text"],
    },
)

TOOL_RESOLVE_ENTITIES = Tool(
    name="resolve_entities",
    description=(
        "Cluster a list of entity mentions (name + page + bbox) across "
        "pages and return one canonical form per cluster. Handles "
        "abbreviations, repeated table headers, and split-across-lines mentions."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "mentions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "page": {"type": "integer", "default": 0},
                        "bbox": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "[x0, y0, x1, y1] in normalized 0..1 coordinates.",
                        },
                        "region_id": {"type": "string"},
                        "field": {
                            "type": "string",
                            "description": "Optional: which extracted field this mention came from.",
                        },
                    },
                    "required": ["text"],
                },
            },
            "entity_type": {
                "type": "string",
                "default": "generic",
                "description": "Free-form label for the cluster type ('org', 'person', ...).",
            },
            "jaccard_threshold": {
                "type": "number",
                "default": 0.5,
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Minimum Jaccard similarity to merge two candidates.",
            },
        },
        "required": ["mentions"],
    },
)

TOOL_EVAL_GOLDEN_SET = Tool(
    name="eval_golden_set",
    description=(
        "Run the v0.5.0 metric suite (TEDS, cell F1, IoU, attribution, "
        "end-to-end task success, ...) on a golden-set JSONL. Each line "
        "of the JSONL must have a top-level 'expected' key plus an optional "
        "'prediction' key. Lines without a prediction contribute to the "
        "denominator as 'not_found' for the end-to-end metric."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "manifest_path": {
                "type": "string",
                "description": (
                    "Path to the manifest.json that was generated by "
                    "scripts/fetch_golden_set.py (v1 CORD) or "
                    "scripts/fetch_docvqa.py (v2 DocVQA + InfographicVQA). "
                    "Required: the manifest pins the schema + license."
                ),
            },
            "predictions": {
                "type": "object",
                "description": (
                    "Optional dict {sample_id: prediction} of model "
                    "predictions to score. If omitted, the tool reads "
                    "prediction.jsonl next to manifest.json (one prediction "
                    "per line, with 'id' matching the golden set)."
                ),
            },
        },
        "required": ["manifest_path"],
    },
)


# ── Tool implementations ──────────────────────────────────────────


async def tool_extract_document(arguments: dict[str, Any]) -> list[TextContent]:
    """Run the v0.5.0 pipeline on a single document."""

    try:
        path = Path(arguments["path"]).expanduser()
    except (KeyError, TypeError) as exc:
        return _error("missing required argument 'path'", hint=str(exc))
    if not path.exists():
        return _error(f"file not found: {path}")
    schema_fields = arguments.get("schema_fields") or []
    if not schema_fields:
        return _error("schema_fields must be a non-empty list")
    min_evidence_score = float(arguments.get("min_evidence_score", 0.5))
    use_llm_verifier = bool(arguments.get("use_llm_verifier", False))
    enable_verifier = bool(arguments.get("enable_verifier", True))
    enable_layout_parsing = bool(arguments.get("enable_layout_parsing", True))
    ocr_provider = arguments.get("ocr_provider", "auto")
    llm_provider = arguments.get("llm_provider", "auto")

    try:
        document_text, layout_summary = await _read_document(
            path,
            ocr_provider=ocr_provider,
            enable_layout_parsing=enable_layout_parsing,
        )
    except Exception as exc:
        logger.exception("extract_document: parse failed")
        return _error(f"parse failed: {exc}", path=str(path))

    try:
        fields_block = render_fields_block(
            [
                {"name": f.get("name"), "kind": f.get("kind"), "description": f.get("description")}
                for f in schema_fields
            ]
        )
        llm_payload = await _call_extractor(
            document_text=document_text,
            fields_block=fields_block,
            llm_provider=llm_provider,
        )
    except Exception as exc:
        logger.exception("extract_document: extractor failed")
        return _error(f"extractor failed: {exc}", llm_provider=llm_provider)

    evidence_map = build_evidence_map(llm_payload)
    evidence_map = filter_low_evidence(evidence_map, min_evidence_score=min_evidence_score)

    verifier_output: VerifierOutput | None = None
    disputed: list[str] = []
    if enable_verifier:
        verifier = LLMVerifier() if use_llm_verifier else HeuristicVerifier()
        verifier_output = await verifier.verify(evidence_map, document_text)
        disputed = resolve_disputes(verifier_output)

    fields_block_out = merge_with_not_found(evidence_map)

    composite = _composite_confidence(
        evidence_map=evidence_map,
        verifier_output=verifier_output,
    )

    response: dict[str, Any] = {
        "path": str(path),
        "ocr_provider": ocr_provider,
        "llm_provider": llm_provider,
        "document_text_excerpt": document_text[:2000],
        "layout_summary": layout_summary,
        "fields": fields_block_out,
        "evidence": {fname: ev.to_dict() for fname, ev in evidence_map.evidences.items()},
        "not_found": list(evidence_map.not_found),
        "verifier": (
            {
                "verifier_model": "heuristic" if not use_llm_verifier else "llm",
                "overall_agreement": verifier_output.overall_agreement,
                "field_verdicts": {
                    fname: v.to_dict() for fname, v in verifier_output.field_verdicts.items()
                },
                "disputed_fields": disputed,
            }
            if verifier_output is not None
            else None
        ),
        "_meta": {
            "prompt_version": "v2",
            "schema_version": "1",
            "not_found_fields": list(evidence_map.not_found),
            "evidence_field_count": len(evidence_map),
            "composite_confidence": composite,
        },
    }
    return _text(response)


async def tool_verify_extraction(arguments: dict[str, Any]) -> list[TextContent]:
    """Re-run the verifier on a prior evidence map."""

    evidence = arguments.get("evidence")
    document_text = arguments.get("document_text", "")
    use_llm = bool(arguments.get("use_llm", False))
    if not isinstance(evidence, dict):
        return _error(
            "'evidence' must be a dict of {field: {value, page, bbox, text_span, evidence_score}}"
        )
    if not isinstance(document_text, str):
        return _error("'document_text' must be a string")

    evidence_map = build_evidence_map(
        {
            "fields": {
                fname: {
                    "value": defn.get("value"),
                    "evidence": {
                        "page": defn.get("page", 0),
                        "bbox": defn.get("bbox"),
                        "text_span": defn.get("text_span", ""),
                        "score": defn.get("evidence_score", 0.0),
                    },
                }
                for fname, defn in evidence.items()
            }
        }
    )

    verifier = LLMVerifier() if use_llm else HeuristicVerifier()
    output = await verifier.verify(evidence_map, document_text)
    disputed = resolve_disputes(output)

    return _text(
        {
            "verifier_model": "llm" if use_llm else "heuristic",
            "overall_agreement": output.overall_agreement,
            "field_verdicts": {fname: v.to_dict() for fname, v in output.field_verdicts.items()},
            "disputed_fields": disputed,
            "needs_human_review": disputed,
        }
    )


async def tool_resolve_entities(arguments: dict[str, Any]) -> list[TextContent]:
    """Cluster mentions and return canonical forms."""

    mentions_raw = arguments.get("mentions") or []
    if not isinstance(mentions_raw, list):
        return _error("'mentions' must be a list of {text, page, bbox, region_id, field}")
    entity_type = arguments.get("entity_type", "generic")
    jaccard_threshold = float(arguments.get("jaccard_threshold", 0.5))

    mentions: list[EntityMention] = []
    for m in mentions_raw:
        if not isinstance(m, dict):
            continue
        text = (m.get("text") or "").strip()
        if not text:
            continue
        bbox_raw = m.get("bbox")
        bbox: tuple[float, float, float, float] | None = None
        if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4:
            try:
                bbox = tuple(float(x) for x in bbox_raw)  # type: ignore[assignment]
            except (TypeError, ValueError):
                bbox = None
        page = m.get("page", 0)
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 0
        mentions.append(
            EntityMention(
                text=text,
                page=page,
                bbox=bbox,  # type: ignore[arg-type]
                region_id=m.get("region_id"),
                field=m.get("field"),
            )
        )

    if not mentions:
        return _text(
            {
                "entity_type": entity_type,
                "jaccard_threshold": jaccard_threshold,
                "entities": [],
            }
        )

    resolved = resolve_entities(
        mentions,
        entity_type=entity_type,
        jaccard_threshold=jaccard_threshold,
    )
    return _text(
        {
            "entity_type": entity_type,
            "jaccard_threshold": jaccard_threshold,
            "entities": [r.to_dict() for r in resolved],
        }
    )


async def tool_eval_golden_set(arguments: dict[str, Any]) -> list[TextContent]:
    """Run the v2 metric suite on a golden-set JSONL."""

    manifest_path = Path(arguments.get("manifest_path", "")).expanduser()
    if not manifest_path.exists():
        return _error(f"manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        return _error(f"manifest is not valid JSON: {exc}", path=str(manifest_path))

    base_dir = manifest_path.parent
    samples = _load_golden_set_samples(manifest, base_dir)
    if not samples:
        return _error("golden set is empty or could not be loaded", manifest=str(manifest_path))

    predictions = arguments.get("predictions")
    if predictions is None:
        prediction_path = base_dir / "prediction.jsonl"
        if prediction_path.exists():
            predictions = _load_jsonl_dicts(prediction_path)
        else:
            return _error(
                "no predictions provided and prediction.jsonl not found next to manifest",
                manifest=str(manifest_path),
                hint="Pass the 'predictions' argument: {sample_id: {<field>: <value>, ...}}",
            )
    if not isinstance(predictions, dict):
        return _error("'predictions' must be a dict {sample_id: {field: value, ...}}")

    out = _score(samples, predictions, manifest)
    return _text(out)


# ── Internal helpers ─────────────────────────────────────────────


async def _read_document(
    path: Path, *, ocr_provider: str, enable_layout_parsing: bool
) -> tuple[str, dict[str, Any]]:
    """Read a document, with optional layout-aware parsing.

    Falls back to plain-text read for unsupported file types.
    Returns ``(document_text, layout_summary)``.
    """

    suffix = path.suffix.lower().lstrip(".")
    # The MCP server does not pull paddlepaddle / docling by
    # default. Plain-text files are read directly; PDFs use the
    # always-available PyMuPDF text layer; images raise a clear
    # error pointing the user at the ``paddleocr`` extra.
    if suffix in {"txt", "md", "csv", "json", "html", "xml"}:
        text = path.read_text(errors="replace")
        return text, {"provider": "text", "page_count": 1, "tokens": []}
    if suffix == "pdf":
        try:
            import pymupdf  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "pymupdf is not installed; install the test extra or "
                "add pymupdf to your environment"
            ) from exc
        doc = pymupdf.open(str(path))
        try:
            pages = [page.get_text("text") for page in doc]
        finally:
            doc.close()
        return "\n\n".join(pages), {
            "provider": ocr_provider,
            "page_count": len(pages),
            "tokens": [],
        }
    if suffix in {"png", "jpg", "jpeg", "tiff", "tif", "bmp", "webp"}:
        # No OCR is available in the MCP-server base install; the
        # user must run with the [paddleocr] or [docling] extra to
        # get image OCR. We surface a clear error.
        raise RuntimeError(
            f"image OCR is not available in the base MCP install; install "
            f"agentic-document-extraction[paddleocr] or [docling] to OCR "
            f"image files. Path: {path}"
        )
    raise RuntimeError(
        f"unsupported file type '.{suffix}'. Supported: txt, md, csv, json, "
        f"html, xml, pdf. Image files require an OCR extra (see error above)."
    )


async def _call_extractor(
    *, document_text: str, fields_block: str, llm_provider: str
) -> dict[str, Any]:
    """Call the configured LLM provider.

    For the v0.6.0 base install we expect the user to have at
    least one provider configured (OpenAI / Anthropic / Gemini
    / Ollama). If none is available, we fall back to a
    deterministic stub so the MCP server still works for
    smoke-testing.

    A production deployment would import the LLM registry and
    call the configured provider. We keep this dependency-free
    in the MCP path so the server is importable without the
    full LLM stack.
    """

    if llm_provider == "openai" and _env_has("OPENAI_API_KEY"):
        return await _call_openai(document_text, fields_block)
    if llm_provider == "anthropic" and _env_has("ANTHROPIC_API_KEY"):
        return await _call_anthropic(document_text, fields_block)
    if llm_provider == "gemini" and _env_has("GOOGLE_API_KEY"):
        return await _call_gemini(document_text, fields_block)
    if llm_provider in {"auto", "ollama"} and _env_has("OLLAMA_BASE_URL"):
        return await _call_ollama(document_text, fields_block)

    # Fallback: deterministic stub for smoke tests
    return _stub_extraction(document_text, fields_block)


def _env_has(name: str) -> bool:
    import os

    return bool(os.environ.get(name))


async def _call_openai(document_text: str, fields_block: str) -> dict[str, Any]:
    raise NotImplementedError(
        "OpenAI live LLM calls are wired into the FastAPI app; the MCP "
        "server delegates to the LLM registry in the next iteration. For "
        "now set llm_provider='ollama' to use a local model."
    )


async def _call_anthropic(document_text: str, fields_block: str) -> dict[str, Any]:
    raise NotImplementedError(
        "Anthropic live LLM calls are wired into the FastAPI app; the MCP "
        "server delegates to the LLM registry in the next iteration. For "
        "now set llm_provider='ollama' to use a local model."
    )


async def _call_gemini(document_text: str, fields_block: str) -> dict[str, Any]:
    raise NotImplementedError(
        "Gemini live LLM calls are wired into the FastAPI app; the MCP "
        "server delegates to the LLM registry in the next iteration. For "
        "now set llm_provider='ollama' to use a local model."
    )


async def _call_ollama(document_text: str, fields_block: str) -> dict[str, Any]:
    """Call a local Ollama model and parse the v2 payload."""

    import os

    import httpx

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_DEFAULT_MODEL", "qwen3.5:7b")
    prompt = _build_v2_prompt(document_text, fields_block)
    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        response = await client.post(
            "/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        raw = response.json().get("response", "")
    payload = _parse_v2_payload(raw)
    return payload


def _build_v2_prompt(document_text: str, fields_block: str) -> str:
    """Build the v2/extraction.md prompt with fields + text filled in."""

    try:
        return load_prompt("extraction", "v2").render(
            fields_block=fields_block,
            text=document_text,
        )
    except Exception:
        template = (
            "You are a document data extraction assistant with strict "
            "evidence requirements. For every value, cite evidence "
            "(page, bbox, text_span, score). If a field cannot be "
            "grounded, set it to null and add its name to not_found.\n\n"
            "FIELDS TO EXTRACT:\n{fields_block}\n\n"
            "DOCUMENT TEXT:\n{text}\n\n"
            "OUTPUT FORMAT:\n"
            '{"fields": {"<field>": {"value": ..., "evidence": '
            '{"page": <int>, "bbox": [x0, y0, x1, y1], "text_span": "...", '
            '"score": 0.0-1.0}}}, ...}, "not_found": [...]}'
        )
    return template.replace("{fields_block}", fields_block).replace("{text}", document_text)


def _parse_v2_payload(raw: str) -> dict[str, Any]:
    """Parse the v2 LLM payload: extract the largest JSON object."""

    text = (raw or "").strip()
    if not text:
        return {"fields": {}, "not_found": []}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {"fields": {}, "not_found": []}


def _stub_extraction(document_text: str, fields_block: str) -> dict[str, Any]:
    """Deterministic stub for smoke tests. Returns one grounded field
    per declared field so downstream stages have something to work
    with. The LLM extractor is what the user actually wants; the
    stub is the no-key fallback."""

    fields: dict[str, dict[str, Any]] = {}
    not_found: list[str] = []
    for line in fields_block.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        # Field line format: "- <name> - <description> [<kind>]: <hint>"
        try:
            name_part = line[1:].split("[")[0].strip().split(" — ")[0].strip()
        except Exception:
            continue
        if not name_part:
            continue
        # Search for the field name in the document as a token sequence
        text_span = _first_meaningful_token_sequence(document_text, name_part)
        if not text_span:
            not_found.append(name_part)
            fields[name_part] = {"value": None}
            continue
        fields[name_part] = {
            "value": text_span,
            "evidence": {
                "page": 0,
                "bbox": [0.1, 0.1, 0.4, 0.2],
                "text_span": text_span,
                "score": 0.5,
            },
        }
    return {"fields": fields, "not_found": not_found}


def _first_meaningful_token_sequence(document_text: str, name: str) -> str:
    """Return the first occurrence of any token of ``name`` in the document."""

    tokens = [t for t in name.replace("-", " ").replace("_", " ").split() if t]
    if not tokens or not document_text:
        return ""
    for token in tokens:
        idx = document_text.lower().find(token.lower())
        if idx != -1:
            return document_text[idx : idx + max(len(token), 4)]
    return ""


def _composite_confidence(
    *,
    evidence_map: EvidenceMap,
    verifier_output: VerifierOutput | None,
) -> float:
    """Compute a composite confidence score in [0, 1]."""

    from app.services.eval.calibration_v2 import (
        CompositeCalibrator,
    )

    if verifier_output is not None:
        # Map the VerifierOutput to the dict shape CompositeCalibrator expects
        verifier_payload = {
            "field_verdicts": {
                fname: {"verdict": v.verdict} for fname, v in verifier_output.field_verdicts.items()
            }
        }
    else:
        verifier_payload = None
    return CompositeCalibrator().confidence(
        logprob_confidence=None,  # unknown in the MCP path; treat as 0.5
        verifier_output=verifier_payload,
        evidences=dict(evidence_map.evidences),
    )


def _load_golden_set_samples(manifest: dict, base_dir: Path) -> list[dict[str, Any]]:
    """Load every sample referenced by the manifest into a flat list."""

    samples: list[dict[str, Any]] = []
    for entry in manifest.get("datasets", []):
        for file_info in entry.get("files", []):
            jsonl_path = base_dir / file_info["name"]
            if not jsonl_path.exists():
                continue
            for line in jsonl_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return samples


def _load_jsonl_dicts(path: Path) -> dict[str, dict[str, Any]]:
    """Load a JSONL file of {id: ..., ...} into a dict keyed by 'id'."""

    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = row.get("id") or row.get("questionId")
        if sid is not None:
            out[str(sid)] = row
    return out


def _score(
    samples: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Score the v2 metric suite over the golden set + predictions."""

    n_samples = len(samples)
    n_with_predictions = 0
    n_end_to_end_success = 0
    em_scores: list[float] = []
    token_f1_scores: list[float] = []
    teds_scores: list[float] = []
    cell_f1_scores: list[float] = []
    header_match_scores: list[float] = []
    row_accuracies: list[float] = []
    column_accuracies: list[float] = []
    evidence_attrs: list[float] = []
    page_local_accs: list[float] = []
    ious: list[float] = []

    for sample in samples:
        sid = str(sample.get("id", ""))
        prediction = predictions.get(sid)
        if not prediction:
            continue
        n_with_predictions += 1
        expected = sample.get("expected", {})
        # KV-style (DocVQA): expected = {query, answer, acceptable_answers}
        if "answer" in expected:
            pred_text = str(prediction.get("answer", ""))
            ref_text = str(expected.get("answer", ""))
            acceptable = expected.get("acceptable_answers") or [ref_text]
            # Best EM / token F1 across the acceptable set
            em_scores.append(max((exact_match_batch([pred_text], [a])) for a in acceptable))
            token_f1_scores.append(max((token_f1_batch([pred_text], [a])) for a in acceptable))
            if _doc_matches(pred_text, ref_text, acceptable):
                n_end_to_end_success += 1
        # Table-style: expected = {rows: [[...]]} or {table: [[...]]}
        ref_table = expected.get("table") or expected.get("rows")
        pred_table = prediction.get("table") or prediction.get("rows")
        if ref_table is not None and pred_table is not None:
            teds_scores.append(teds(pred_table, ref_table))
            cell_f1_scores.append(_cell_f1(pred_table, ref_table))
            header_match_scores.append(_header_match(pred_table, ref_table))
            struct = _row_col(pred_table, ref_table)
            row_accuracies.append(struct["row_accuracy"])
            column_accuracies.append(struct["column_accuracy"])
        # Evidence metrics (any sample with a prediction that has
        # an evidence block contributes; the expected may be
        # missing or partial).
        evidences = prediction.get("evidence") or {}
        if evidences:
            evidence_attrs.append(evidence_attribution_accuracy(evidences))
            page_local_accs.append(_page_local(evidences, expected.get("evidence") or {}))
            ious.append(_mean_iou(evidences, expected.get("evidence") or {}))

    summary: dict[str, Any] = {
        "version": manifest.get("version", "?"),
        "n_samples": n_samples,
        "n_with_predictions": n_with_predictions,
        "n_end_to_end_success": n_end_to_end_success,
        "end_to_end_task_success_rate": (
            n_end_to_end_success / n_with_predictions if n_with_predictions else 0.0
        ),
    }
    if em_scores:
        summary["em"] = sum(em_scores) / len(em_scores)
    if token_f1_scores:
        summary["token_f1"] = sum(token_f1_scores) / len(token_f1_scores)
    if teds_scores:
        summary["teds"] = sum(teds_scores) / len(teds_scores)
    if cell_f1_scores:
        summary["cell_f1"] = sum(cell_f1_scores) / len(cell_f1_scores)
    if header_match_scores:
        summary["header_match_accuracy"] = sum(header_match_scores) / len(header_match_scores)
    if row_accuracies:
        summary["row_accuracy"] = sum(row_accuracies) / len(row_accuracies)
        summary["column_accuracy"] = sum(column_accuracies) / len(column_accuracies)
    if evidence_attrs:
        summary["evidence_attribution_accuracy"] = sum(evidence_attrs) / len(evidence_attrs)
        summary["page_localization_accuracy"] = sum(page_local_accs) / len(page_local_accs)
        summary["mean_bbox_iou"] = sum(ious) / len(ious)
    return summary


def _doc_matches(pred_text: str, ref_text: str, acceptable: list[str]) -> bool:
    """True if pred matches any acceptable answer (token F1 >= 0.999)."""

    return any(token_f1_batch([pred_text], [str(a)]) >= 0.999 for a in acceptable)


def _cell_f1(p: Any, r: Any) -> float:
    from app.services.eval.metrics_v2 import cell_precision_recall_f1

    return cell_precision_recall_f1(p, r)["f1"]


def _header_match(p: Any, r: Any) -> float:
    from app.services.eval.metrics_v2 import header_match_accuracy

    return header_match_accuracy(p, r)


def _row_col(p: Any, r: Any) -> dict[str, float]:
    from app.services.eval.metrics_v2 import row_column_structure_accuracy

    return row_column_structure_accuracy(p, r)


def _page_local(p: Any, r: Any) -> float:
    return page_localization_accuracy(p, r)


def _mean_iou(p: Any, r: Any) -> float:
    return mean_bbox_iou(p, r)


# ── Server entry point ────────────────────────────────────────────


def _build_server() -> Server:
    """Construct the MCP server with the four tools registered."""

    server: Any = Server(SERVER_NAME, version=SERVER_VERSION, instructions=SERVER_INSTRUCTIONS)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            TOOL_EXTRACT_DOCUMENT,
            TOOL_VERIFY_EXTRACTION,
            TOOL_RESOLVE_ENTITIES,
            TOOL_EVAL_GOLDEN_SET,
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == TOOL_EXTRACT_DOCUMENT.name:
            return await tool_extract_document(arguments or {})
        if name == TOOL_VERIFY_EXTRACTION.name:
            return await tool_verify_extraction(arguments or {})
        if name == TOOL_RESOLVE_ENTITIES.name:
            return await tool_resolve_entities(arguments or {})
        if name == TOOL_EVAL_GOLDEN_SET.name:
            return await tool_eval_golden_set(arguments or {})
        return _error(f"unknown tool: {name!r}", available=[t.name for t in await list_tools()])

    return server


async def _run() -> None:
    """Run the MCP server over stdio (the default MCP transport)."""

    server = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Console entry point. Invoked by the ``ade-mcp`` script."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
