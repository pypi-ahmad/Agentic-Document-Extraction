"""Paperplane's local Streamlit workspace."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import bleach
import httpx
import streamlit as st
from dotenv import load_dotenv

import paperplane.runtime as runtime
from paperplane.ade_contracts import EngineOptions, to_ade_v2_parse, to_paperplane_export
from paperplane.annotated_pdf import AnnotatedPdfArtifact, build_annotated_pdf
from paperplane.contracts import ParseResponse, ProcessingStrategy, StructureNode
from paperplane.ingest import IMAGE_EXTENSIONS, OFFICE_EXTENSIONS, inspect_document
from paperplane.jobs import JobStore
from paperplane.model_catalog import (
    DEFAULT_DOCUMENT_MODEL,
    DOCUMENT_MODEL_BY_ID,
    DOCUMENT_MODEL_BY_LABEL,
    DOCUMENT_MODELS,
    estimate_model_cost,
)
from paperplane.ollama_document import OllamaDocumentAdapter, OllamaModel, OllamaRequestError
from paperplane.outputs import (
    OutputArchiveEntry,
    build_output_archive,
    safe_output_stem,
    sanitized_html_fragment,
    standalone_html,
)

APP_VERSION = "5.0.2"
QUALITY_LABELS = {
    "Fast": "paperplane-ade-fast-latest",
    "Balanced": "paperplane-ade-latest",
    "Audit": "paperplane-ade-audit-latest",
}
QUALITY_HELP = {
    "Fast": "Straightforward documents with deterministic grounding.",
    "Balanced": "Adaptive verification for most documents.",
    "Audit": "Maximum inspection depth for difficult pages.",
}
ENGINE_LABELS = {
    "docling": "Docling ADE",
    "pdf_inspector": "PDF Inspector ADE",
    "cloud_ai": "Cloud AI ADE",
    "ollama": "Ollama ADE",
}
AI_STRATEGIES = {"ai", "docling_ai", "pdf_inspector_ai", "ollama_ai"}
AI_MODEL_LABELS = [model.label for model in DOCUMENT_MODELS]
SUPPORTED_EXTENSIONS = [
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "tif",
    "tiff",
    "bmp",
    "docx",
    "pptx",
    "xlsx",
    "odt",
    "odp",
    "ods",
    "csv",
]
SAFE_HTML_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "caption",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
}
SAFE_HTML_ATTRIBUTES = {
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
}

load_dotenv(override=False)


def _secret(name: str) -> str:
    try:
        value: Any = st.secrets.get(name, "")
    except FileNotFoundError:
        return ""
    return str(value).strip() if value is not None else ""


def _setting(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or _secret(name) or default


def _job_store() -> JobStore:
    local_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    root = local_root / "Paperplane"
    return JobStore(root / "paperplane.sqlite3", root / "artifacts", ttl_days=7)


def _count_blocks(node: StructureNode) -> int:
    own = 0 if node.type in {"document", "page"} else 1
    return own + sum(_count_blocks(child) for child in node.children)


def _format_cost_usd(value: Decimal) -> str:
    return f"${value:.6f}" if value < 1 else f"${value:.4f}"


def _safe_rendered_markdown(value: str) -> str:
    return bleach.clean(
        value,
        tags=SAFE_HTML_TAGS,
        attributes=SAFE_HTML_ATTRIBUTES,
        strip=True,
    )


def _file_id(index: int, filename: str, data: bytes) -> str:
    digest = hashlib.sha256(filename.encode("utf-8") + b"\0" + data).hexdigest()[:16]
    return f"{index}-{digest}"


def _reset_results() -> None:
    st.session_state.batch_outcomes = []
    st.session_state.annotated_pdfs = {}
    st.session_state.artifact_errors = {}
    st.session_state.selected_document_id = None
    st.session_state.workspace_view = "Input preview"


def _clear_workspace() -> None:
    st.session_state.upload_generation += 1
    st.session_state.upload_signature = None
    _reset_results()


def _activate_engine(engine: str) -> None:
    if not st.session_state.get(f"engine_{engine}", False):
        return
    for candidate in ENGINE_LABELS:
        if candidate != engine:
            st.session_state[f"engine_{candidate}"] = False
    if engine == "cloud_ai":
        st.session_state.cloud_enhancement = False


async def _discover_ollama(base_url: str) -> list[OllamaModel]:
    async with httpx.AsyncClient(timeout=10) as client:
        return await OllamaDocumentAdapter(client, base_url=base_url).list_models()


@st.cache_data(ttl=15, show_spinner=False)
def _cached_ollama_models(base_url: str) -> list[OllamaModel]:
    return asyncio.run(_discover_ollama(base_url))


async def _build_artifacts(
    outcomes: list[runtime.BatchParseOutcome],
    sources: dict[str, tuple[bytes, str]],
) -> tuple[dict[str, AnnotatedPdfArtifact], dict[str, str]]:
    artifacts: dict[str, AnnotatedPdfArtifact] = {}
    errors: dict[str, str] = {}

    async def build(outcome: runtime.BatchParseOutcome) -> None:
        if outcome.result is None:
            return
        data, filename = sources[outcome.file_id]
        try:
            artifacts[outcome.file_id] = await asyncio.to_thread(
                build_annotated_pdf,
                source=data,
                filename=filename,
                response=outcome.result,
            )
        except Exception:
            errors[outcome.file_id] = (
                "The parse completed, but the annotated PDF could not be generated."
            )

    await asyncio.gather(*(build(outcome) for outcome in outcomes))
    return artifacts, errors


def _result_cost(result: ParseResponse) -> Decimal | None:
    model = DOCUMENT_MODEL_BY_ID.get(result.metadata.ai_model or "")
    if model is None:
        return Decimal("0") if not result.metadata.ai_model else None
    return estimate_model_cost(
        model.model_id,
        input_tokens=result.metadata.input_tokens,
        output_tokens=result.metadata.output_tokens,
        cached_input_tokens=result.metadata.cached_input_tokens,
    ).total_cost_usd


def _render_result_overview(outcome: runtime.BatchParseOutcome) -> None:
    result = outcome.result
    if result is None:
        return
    st.subheader(outcome.filename)
    ai_model = DOCUMENT_MODEL_BY_ID.get(result.metadata.ai_model or "")
    cost = _result_cost(result)
    metrics = st.columns(5)
    metrics[0].metric("Pages", result.metadata.page_count)
    metrics[1].metric("Blocks", _count_blocks(result.structure))
    metrics[2].metric("Engine", result.metadata.engine.replace("_", " ").title())
    metrics[3].metric("Duration", f"{result.metadata.duration_ms or 0} ms")
    metrics[4].metric(
        "Estimated cost",
        _format_cost_usd(cost) if cost is not None else "Unavailable",
    )
    page_range = result.metadata.page_range
    range_text = f"pages {page_range[0]}-{page_range[1]}" if page_range else "all pages"
    st.caption(
        f"{result.metadata.output_characters:,} characters · {range_text} · "
        f"{result.metadata.source_format.upper()} source · "
        f"{result.metadata.input_tokens:,} input tokens · "
        f"{result.metadata.output_tokens:,} output tokens"
    )
    if result.metadata.ai_refined_pages:
        st.caption("AI-refined pages: " + ", ".join(map(str, result.metadata.ai_refined_pages)))
    for warning in result.metadata.warnings:
        st.warning(warning)

    if ai_model is not None and cost is not None:
        with st.expander("Cost calculation"):
            estimate = estimate_model_cost(
                ai_model.model_id,
                input_tokens=result.metadata.input_tokens,
                output_tokens=result.metadata.output_tokens,
                cached_input_tokens=result.metadata.cached_input_tokens,
            )
            st.write(f"**{ai_model.label}** (`{ai_model.model_id}`)")
            st.write(
                f"Input: {_format_cost_usd(estimate.input_cost_usd)} at "
                f"${ai_model.input_price_per_million}/1M tokens"
            )
            st.write(
                f"Output: {_format_cost_usd(estimate.output_cost_usd)} at "
                f"${ai_model.output_price_per_million}/1M tokens"
            )
            st.caption(f"Estimate only. {ai_model.pricing_note}")


def _render_source_preview(filename: str, data: bytes) -> None:
    suffix = Path(filename).suffix.casefold()
    if suffix == ".pdf":
        st.pdf(data, height=760, key=f"source_pdf_{hashlib.sha256(data).hexdigest()[:12]}")
    elif suffix in IMAGE_EXTENSIONS:
        st.image(data, caption=filename, width="stretch")
    else:
        st.info(
            f"{filename} is ready. Its visual preview appears after conversion.",
            icon=":material/draft:",
        )


def _archive_entries(
    outcomes: list[runtime.BatchParseOutcome],
    artifacts: dict[str, AnnotatedPdfArtifact],
    artifact_errors: dict[str, str],
) -> tuple[OutputArchiveEntry, ...]:
    entries: list[OutputArchiveEntry] = []
    for outcome in outcomes:
        result = outcome.result
        if result is None:
            entries.append(
                OutputArchiveEntry(
                    filename=outcome.filename,
                    status="failed",
                    error=outcome.error or "Parsing failed",
                )
            )
            continue
        artifact = artifacts.get(outcome.file_id)
        result_json = json.dumps(
            to_paperplane_export(result).model_dump(mode="json", exclude_none=True), indent=2
        )
        ade_json = json.dumps(
            to_ade_v2_parse(result).model_dump(mode="json", exclude_none=True), indent=2
        )
        entries.append(
            OutputArchiveEntry(
                filename=outcome.filename,
                status="completed",
                error=artifact_errors.get(outcome.file_id),
                markdown=result.markdown,
                html=standalone_html(result.markdown, outcome.filename),
                annotated_pdf=artifact.data if artifact is not None else None,
                paperplane_json=result_json,
                ade_v2_json=ade_json,
            )
        )
    return tuple(entries)


@st.cache_data(max_entries=2, show_spinner=False)
def _cached_output_archive(entries: tuple[OutputArchiveEntry, ...]) -> bytes:
    return build_output_archive(entries)


for key, default in {
    "upload_generation": 0,
    "upload_signature": None,
    "batch_outcomes": [],
    "annotated_pdfs": {},
    "artifact_errors": {},
    "selected_document_id": None,
    "workspace_view": "Input preview",
    "json_format": "Paperplane",
    "engine_docling": False,
    "engine_pdf_inspector": False,
    "engine_cloud_ai": False,
    "engine_ollama": False,
    "cloud_enhancement": False,
}.items():
    st.session_state.setdefault(key, default)

api_keys = {model.api_key_env: _setting(model.api_key_env) for model in DOCUMENT_MODELS}
openai_base_url = _setting("OPENAI_BASE_URL", runtime.DEFAULT_OPENAI_BASE_URL)
job_store = _job_store()
job_store.purge_expired()

with st.container(horizontal=True, vertical_alignment="center"):
    st.title("Paperplane")
    st.badge("Private local workspace", icon=":material/lock:", color="blue")
st.caption(
    "Turn PDFs, images, and modern Office documents into layout-aware Markdown "
    "with hierarchical grounding JSON."
)

with st.sidebar, st.container(border=True):
    st.subheader("New parse")
    st.write("**Processing engine**")
    for engine_name, label in ENGINE_LABELS.items():
        st.toggle(
            label,
            key=f"engine_{engine_name}",
            on_change=_activate_engine,
            args=(engine_name,),
        )
    options = EngineOptions(
        docling=st.session_state.engine_docling,
        pdf_inspector=st.session_state.engine_pdf_inspector,
        cloud_ai=st.session_state.engine_cloud_ai,
        ollama=st.session_state.engine_ollama,
        cloud_enhancement=st.session_state.cloud_enhancement,
    )
    selected_engine = options.selected_engine
    if selected_engine is None:
        st.info("Choose one processing engine. No engine is selected initially.")

    cloud_enhancement = False
    if selected_engine in {"docling", "pdf_inspector", "ollama"}:
        cloud_enhancement = st.toggle(
            "Enhance with cloud AI after the selected engine",
            key="cloud_enhancement",
        )
    elif st.session_state.cloud_enhancement:
        st.session_state.cloud_enhancement = False

    strategy: ProcessingStrategy = (
        "docling_ai"
        if selected_engine == "docling" and cloud_enhancement
        else "docling"
        if selected_engine == "docling"
        else "pdf_inspector_ai"
        if selected_engine == "pdf_inspector" and cloud_enhancement
        else "pdf_inspector"
        if selected_engine == "pdf_inspector"
        else "ollama_ai"
        if selected_engine == "ollama" and cloud_enhancement
        else "ollama"
        if selected_engine == "ollama"
        else "ai"
    )

    selected_ai_model = DOCUMENT_MODEL_BY_ID[DEFAULT_DOCUMENT_MODEL]
    selected_quality = "Balanced"
    api_key = ""
    ollama_model = "glm-ocr:latest"
    ollama_base_url = _setting("OLLAMA_BASE_URL", runtime.DEFAULT_OLLAMA_BASE_URL)
    ollama_ready = True
    if selected_engine == "ollama":
        try:
            ollama_models = _cached_ollama_models(ollama_base_url)
        except OllamaRequestError as exc:
            ollama_models = []
            ollama_ready = False
            st.warning(str(exc), icon=":material/computer_off:")
        if ollama_models:
            names = [item.name for item in ollama_models]
            ollama_model = st.selectbox("Ollama model", names)
            selected_local = next(item for item in ollama_models if item.name == ollama_model)
            if not selected_local.vision_capable:
                ollama_ready = False
                st.error(
                    "This installed model does not report the `vision` capability. "
                    "It remains visible, but document Parse is disabled."
                )

    if selected_engine == "cloud_ai" or cloud_enhancement:
        selected_ai_label = st.selectbox(
            "Cloud AI model",
            AI_MODEL_LABELS,
            index=AI_MODEL_LABELS.index(selected_ai_model.label),
        )
        selected_ai_model = DOCUMENT_MODEL_BY_LABEL[selected_ai_label]
        api_key = api_keys[selected_ai_model.api_key_env]
        if not api_key:
            st.warning(
                f"Set `{selected_ai_model.api_key_env}` to use this AI strategy.",
                icon=":material/key:",
            )
        st.caption(f"`{selected_ai_model.model_id}` · {selected_ai_model.help_text}")
        selected_quality = st.segmented_control(
            "AI quality",
            list(QUALITY_LABELS),
            default="Balanced",
            key="processing_mode",
        )
        if selected_quality not in QUALITY_LABELS:
            st.error("Select an AI quality mode.")
            st.stop()
        st.caption(QUALITY_HELP[selected_quality])

    uploaded_files = st.file_uploader(
        "Choose documents",
        type=SUPPORTED_EXTENSIONS,
        accept_multiple_files=True,
        max_upload_size=200,
        key=f"document_upload_{st.session_state.upload_generation}",
        help="Up to 20 files and 1 GiB combined; maximum 200 MiB and 500 pages per file.",
    )
    uploads = [
        (_file_id(index, Path(upload.name).name, upload.getvalue()), upload, upload.getvalue())
        for index, upload in enumerate(uploaded_files)
    ]
    signature = tuple(file_id for file_id, _upload, _data in uploads)
    if signature != st.session_state.upload_signature:
        st.session_state.upload_signature = signature
        _reset_results()

    page_ranges: dict[str, tuple[int, int | None]] = {}
    preflight_errors: list[str] = []
    for file_id, upload, data in uploads:
        filename = Path(upload.name).name or "document"
        page_count: int | None = None
        if Path(filename).suffix.casefold() not in OFFICE_EXTENSIONS:
            try:
                page_count = inspect_document(
                    data,
                    filename,
                    runtime.MAX_BATCH_BYTES,
                    500,
                ).page_count
            except ValueError as exc:
                preflight_errors.append(f"{filename}: {exc}")
        with st.expander(filename):
            if page_count is not None:
                st.caption(f"{page_count} page{'s' if page_count != 1 else ''}")
            else:
                st.caption("Page count will be determined after Office conversion.")
            page_start = st.number_input(
                f"Start page — {filename}",
                min_value=1,
                value=1,
                step=1,
                key=f"page_start_{file_id}",
            )
            page_end = st.number_input(
                f"End page — {filename}",
                min_value=1,
                value=page_count,
                step=1,
                key=f"page_end_{file_id}",
                placeholder="Last page",
            )
            page_ranges[file_id] = (
                int(page_start),
                int(page_end) if page_end is not None else None,
            )

    total_bytes = sum(len(data) for _file_id_value, _upload, data in uploads)
    if selected_engine is None:
        preflight_errors.append("Choose one processing engine.")
    if len(uploads) > runtime.MAX_BATCH_FILES:
        preflight_errors.append(f"Choose no more than {runtime.MAX_BATCH_FILES} files.")
    if total_bytes > runtime.MAX_BATCH_BYTES:
        preflight_errors.append("Combined upload size exceeds 1 GiB.")
    if strategy.startswith("pdf_inspector") and any(
        Path(upload.name).suffix.casefold() != ".pdf" for _id, upload, _data in uploads
    ):
        preflight_errors.append("PDF Inspector strategies accept PDF files only.")
    if (
        selected_engine is not None
        and strategy in AI_STRATEGIES
        and not api_key
        and strategy != "ollama"
    ):
        preflight_errors.append(f"{selected_ai_model.api_key_env} is required.")
    if selected_engine == "ollama" and not ollama_ready:
        preflight_errors.append("Choose a vision-capable Ollama model.")
    for message in preflight_errors:
        st.error(message)

    with st.container(horizontal=True):
        parse_clicked = st.button(
            "Parse files",
            type="primary",
            icon=":material/document_scanner:",
            disabled=not uploads or bool(preflight_errors),
        )
        st.button("New parse", icon=":material/note_add:", on_click=_clear_workspace)

processing_slot = st.container()
if parse_clicked:
    durable_jobs = {}
    for file_id, upload, data in uploads:
        durable = job_store.create_job(
            filename=Path(upload.name).name or "document",
            engine=selected_engine or "unknown",
            page_range=page_ranges[file_id],
        )
        job_store.mark_running(durable.id)
        job_store.save_artifact(durable.id, Path(upload.name).name or "source.bin", data)
        durable_jobs[file_id] = durable.id
    requests = [
        runtime.BatchParseRequest(
            file_id=file_id,
            data=data,
            filename=Path(upload.name).name or "document",
            model=QUALITY_LABELS[selected_quality],
            ai_model=selected_ai_model.model_id,
            api_key=api_key,
            openai_base_url=openai_base_url,
            strategy=strategy,
            page_start=page_ranges[file_id][0],
            page_end=page_ranges[file_id][1],
            ollama_model=ollama_model,
            ollama_base_url=ollama_base_url,
        )
        for file_id, upload, data in uploads
    ]
    with processing_slot, st.status("Processing documents in parallel…", expanded=True) as status:
        outcomes = asyncio.run(runtime.parse_documents(requests))
        sources = {
            file_id: (data, Path(upload.name).name or "document")
            for file_id, upload, data in uploads
        }
        artifacts, artifact_errors = asyncio.run(_build_artifacts(outcomes, sources))
        st.session_state.batch_outcomes = outcomes
        st.session_state.annotated_pdfs = artifacts
        st.session_state.artifact_errors = artifact_errors
        for outcome in outcomes:
            durable_id = durable_jobs[outcome.file_id]
            if outcome.result is None:
                job_store.fail_job(durable_id, outcome.error or "Parsing failed")
                continue
            result_payload = to_paperplane_export(outcome.result).model_dump(
                mode="json", exclude_none=True
            )
            job_store.save_artifact(
                durable_id,
                "result.json",
                json.dumps(result_payload, indent=2).encode("utf-8"),
            )
            artifact = artifacts.get(outcome.file_id)
            if artifact is not None:
                job_store.save_artifact(durable_id, "annotated.pdf", artifact.data)
            job_store.complete_job(
                durable_id,
                result={
                    "filename": outcome.filename,
                    "pages": outcome.result.metadata.page_count,
                    "engine": outcome.result.metadata.engine,
                },
            )
        selected = next((item for item in outcomes if item.result is not None), outcomes[0])
        st.session_state.selected_document_id = selected.file_id
        st.session_state.workspace_view = "Output"
        status.update(label="Batch complete", state="complete", expanded=False)

outcomes = st.session_state.batch_outcomes
outcomes_by_id = {outcome.file_id: outcome for outcome in outcomes}
uploads_by_id = {
    file_id: (Path(upload.name).name or "document", data) for file_id, upload, data in uploads
}
document_ids = list(uploads_by_id) or list(outcomes_by_id)
if document_ids:
    if st.session_state.selected_document_id not in document_ids:
        st.session_state.selected_document_id = document_ids[0]
    selected_id = st.selectbox(
        "Document",
        document_ids,
        format_func=lambda file_id: (
            uploads_by_id[file_id][0]
            if file_id in uploads_by_id
            else outcomes_by_id[file_id].filename
        ),
        key="selected_document_id",
    )
else:
    selected_id = None

input_tab, output_tab, pdf_tab, markdown_tab, html_tab, json_tab = st.tabs(
    ["Input preview", "Output", "Annotated PDF", "Markdown", "HTML", "JSON"],
    key="workspace_view",
    on_change="rerun",
)
selected_outcome = outcomes_by_id.get(selected_id) if selected_id is not None else None
selected_result = selected_outcome.result if selected_outcome is not None else None
selected_artifact = (
    st.session_state.annotated_pdfs.get(selected_id) if selected_id is not None else None
)
selected_artifact_error = (
    st.session_state.artifact_errors.get(selected_id) if selected_id is not None else None
)

if input_tab.open:
    with input_tab:
        if selected_id is None or selected_id not in uploads_by_id:
            st.info(
                "Choose PDFs, images, Office documents, OpenDocument files, or CSV files to begin.",
                icon=":material/upload_file:",
            )
        else:
            filename, source_data = uploads_by_id[selected_id]
            _render_source_preview(filename, source_data)

if output_tab.open:
    with output_tab:
        if outcomes:
            rows = []
            total_cost = Decimal("0")
            for outcome in outcomes:
                result = outcome.result
                cost = _result_cost(result) if result is not None else None
                if cost is not None:
                    total_cost += cost
                rows.append(
                    {
                        "File": outcome.filename,
                        "Status": "Completed" if result is not None else "Failed",
                        "Pages": result.metadata.page_count if result is not None else "—",
                        "Engine": result.metadata.engine if result is not None else "—",
                        "Cost": _format_cost_usd(cost) if cost is not None else "—",
                        "Error": outcome.error or "",
                    }
                )
            st.subheader("Batch summary")
            st.dataframe(rows, hide_index=True)
            st.caption(f"Estimated batch cost: {_format_cost_usd(total_cost)}")
        if selected_result is not None and selected_outcome is not None:
            _render_result_overview(selected_outcome)
            st.markdown(_safe_rendered_markdown(selected_result.markdown), unsafe_allow_html=True)
        elif selected_outcome is not None:
            st.error(selected_outcome.error or "Parsing failed.")
        else:
            st.info("Parse the selected document to view its layout-aware output.")

if pdf_tab.open:
    with pdf_tab:
        if selected_artifact is not None and selected_id is not None:
            if selected_artifact.kind == "source_overlay":
                st.caption(
                    f"{selected_artifact.annotated_blocks} grounded blocks are overlaid on source pages."
                )
            else:
                st.caption("Semantic-only blocks are listed without invented coordinates.")
            st.pdf(selected_artifact.data, height=720, key=f"annotated_pdf_{selected_id}")
        elif selected_artifact_error:
            st.error(selected_artifact_error)
        else:
            st.info("No annotated PDF is available for the selected document.")

if markdown_tab.open:
    with markdown_tab:
        if selected_result is not None:
            st.code(selected_result.markdown, language="markdown", wrap_lines=True)
        else:
            st.info("No Markdown is available for the selected document.")

if html_tab.open:
    with html_tab:
        if selected_result is not None and selected_outcome is not None:
            st.caption("Sanitized standalone HTML generated from the layout-aware Markdown.")
            st.html(sanitized_html_fragment(selected_result.markdown))
        else:
            st.info("No HTML is available for the selected document.")

if json_tab.open:
    with json_tab:
        if selected_result is not None:
            json_format = st.segmented_control(
                "JSON format",
                ["Paperplane", "ADE v2"],
                key="json_format",
            )
            payload = (
                to_ade_v2_parse(selected_result).model_dump(mode="json")
                if json_format == "ADE v2"
                else to_paperplane_export(selected_result).model_dump(mode="json")
            )
            st.json(payload, expanded=2)
        else:
            st.info("No JSON is available for the selected document.")

archive_entries = _archive_entries(
    outcomes,
    st.session_state.annotated_pdfs,
    st.session_state.artifact_errors,
)
if selected_result is not None and selected_outcome is not None:
    stem = safe_output_stem(selected_outcome.filename)
    result_json = json.dumps(
        to_paperplane_export(selected_result).model_dump(mode="json", exclude_none=True), indent=2
    )
    ade_json = json.dumps(
        to_ade_v2_parse(selected_result).model_dump(mode="json", exclude_none=True), indent=2
    )
    html_output = standalone_html(selected_result.markdown, selected_outcome.filename)
    with st.container(horizontal=True):
        st.download_button(
            "Download Markdown",
            selected_result.markdown,
            file_name=f"{stem}.md",
            mime="text/markdown",
            icon=":material/download:",
        )
        st.download_button(
            "Download HTML",
            html_output,
            file_name=f"{stem}.html",
            mime="text/html",
            icon=":material/code:",
        )
        if selected_artifact is not None:
            st.download_button(
                "Download annotated PDF",
                selected_artifact.data,
                file_name=f"{stem}.annotated.pdf",
                mime="application/pdf",
                icon=":material/picture_as_pdf:",
            )
        st.download_button(
            "Download Paperplane JSON",
            result_json,
            file_name=f"{stem}.paperplane.json",
            mime="application/json",
            icon=":material/download:",
        )
        st.download_button(
            "Download ADE v2 JSON",
            ade_json,
            file_name=f"{stem}.ade-v2.json",
            mime="application/json",
            icon=":material/data_object:",
        )
        if archive_entries:
            st.download_button(
                "Download batch ZIP",
                _cached_output_archive(archive_entries),
                file_name="paperplane-output-batch.zip",
                mime="application/zip",
                icon=":material/folder_zip:",
            )
elif archive_entries:
    st.download_button(
        "Download batch ZIP",
        _cached_output_archive(archive_entries),
        file_name="paperplane-output-batch.zip",
        mime="application/zip",
        icon=":material/folder_zip:",
    )

st.caption(f"Paperplane v{APP_VERSION} · Durable job metadata and artifacts expire after 7 days.")
