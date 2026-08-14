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
import streamlit as st
from dotenv import load_dotenv

import paperplane.runtime as runtime
from paperplane.annotated_pdf import AnnotatedPdfArtifact, build_annotated_pdf
from paperplane.contracts import ParseResponse, StructureNode
from paperplane.ingest import DocumentInputError
from paperplane.model_catalog import (
    DEFAULT_DOCUMENT_MODEL,
    DOCUMENT_MODEL_BY_ID,
    DOCUMENT_MODEL_BY_LABEL,
    DOCUMENT_MODELS,
    estimate_model_cost,
)
from paperplane.openai_document import OpenAIRequestError

APP_VERSION = "4.2.0"
MODEL_LABELS = {
    "Fast": "paperplane-ade-fast-latest",
    "Balanced": "paperplane-ade-latest",
    "Audit": "paperplane-ade-audit-latest",
}
MODEL_HELP = {
    "Fast": "Straightforward documents with deterministic grounding.",
    "Balanced": "Adaptive verification for most documents.",
    "Audit": "Maximum inspection depth for difficult pages.",
}
AI_MODEL_LABELS = [model.label for model in DOCUMENT_MODELS]
IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
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

st.set_page_config(
    page_title="Paperplane",
    page_icon=":material/description:",
    layout="wide",
)


def _secret(name: str) -> str:
    try:
        value: Any = st.secrets.get(name, "")
    except FileNotFoundError:
        return ""
    return str(value).strip() if value is not None else ""


def _setting(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or _secret(name) or default


def _count_blocks(node: StructureNode) -> int:
    own = 0 if node.type in {"document", "page"} else 1
    return own + sum(_count_blocks(child) for child in node.children)


def _format_cost_usd(value: Decimal) -> str:
    return f"${value:.6f}" if value < 1 else f"${value:.4f}"


def _clear_workspace() -> None:
    st.session_state.upload_generation += 1
    st.session_state.result = None
    st.session_state.result_filename = None
    st.session_state.document_hash = None
    st.session_state.error_message = None
    st.session_state.annotated_pdf = None
    st.session_state.artifact_error = None
    st.session_state.result_view = "Output"


def _safe_rendered_markdown(value: str) -> str:
    return bleach.clean(
        value,
        tags=SAFE_HTML_TAGS,
        attributes=SAFE_HTML_ATTRIBUTES,
        strip=True,
    )


st.session_state.setdefault("upload_generation", 0)
st.session_state.setdefault("result", None)
st.session_state.setdefault("result_filename", None)
st.session_state.setdefault("document_hash", None)
st.session_state.setdefault("error_message", None)
st.session_state.setdefault("annotated_pdf", None)
st.session_state.setdefault("artifact_error", None)
st.session_state.setdefault("result_view", "Output")

api_keys = {model.api_key_env: _setting(model.api_key_env) for model in DOCUMENT_MODELS}
openai_base_url = _setting("OPENAI_BASE_URL", runtime.DEFAULT_OPENAI_BASE_URL)

with st.container(horizontal=True, vertical_alignment="center"):
    st.title("Paperplane")
    st.badge("Local and stateless", icon=":material/lock:", color="blue")
st.caption(
    "Turn PDFs, images, and modern Office documents into layout-aware Markdown "
    "with hierarchical grounding JSON."
)

preview_column, workspace_column = st.columns([1.15, 1], gap="large")

with workspace_column:
    with st.container(border=True):
        st.subheader("New parse")
        default_model_label = DOCUMENT_MODEL_BY_ID[DEFAULT_DOCUMENT_MODEL].label
        selected_ai_label = st.selectbox(
            "AI model",
            AI_MODEL_LABELS,
            index=AI_MODEL_LABELS.index(default_model_label),
        )
        selected_ai_model = DOCUMENT_MODEL_BY_LABEL[selected_ai_label]
        api_key = api_keys[selected_ai_model.api_key_env]
        if not api_key:
            st.warning(
                "Local Office and native-PDF parsing is available. Set "
                f"`{selected_ai_model.api_key_env}` to parse "
                "scans and images or describe figures.",
                icon=":material/key:",
            )
        st.caption(f"`{selected_ai_model.model_id}` · {selected_ai_model.help_text}")
        selected_label = st.segmented_control(
            "Processing mode",
            list(MODEL_LABELS),
            default="Balanced",
            key="processing_mode",
        )
        if selected_label not in MODEL_LABELS:
            st.error("Select a valid processing mode.")
            st.stop()
        st.caption(MODEL_HELP[selected_label])

        uploaded = st.file_uploader(
            "Choose a document",
            type=SUPPORTED_EXTENSIONS,
            max_upload_size=200,
            key=f"document_upload_{st.session_state.upload_generation}",
            help=(
                "PDF; PNG/JPEG/WebP/TIFF/BMP; DOCX/PPTX/XLSX; ODT/ODP/ODS; or CSV. "
                "Maximum 200 MB and 500 pages."
            ),
        )

        uploaded_data = uploaded.getvalue() if uploaded is not None else None
        uploaded_hash = hashlib.sha256(uploaded_data).hexdigest() if uploaded_data else None
        if uploaded_hash != st.session_state.document_hash:
            st.session_state.document_hash = uploaded_hash
            st.session_state.result = None
            st.session_state.result_filename = None
            st.session_state.error_message = None
            st.session_state.annotated_pdf = None
            st.session_state.artifact_error = None
            st.session_state.result_view = "Output"

        with st.container(horizontal=True):
            parse_clicked = st.button(
                "Parse document",
                type="primary",
                icon=":material/document_scanner:",
                disabled=uploaded is None,
            )
            st.button(
                "New extraction",
                icon=":material/note_add:",
                on_click=_clear_workspace,
            )

    result_slot = st.container()

    if parse_clicked and uploaded is not None and uploaded_data is not None:
        filename = Path(uploaded.name).name or "document"
        try:
            with st.status("Parsing document…", expanded=True) as status:
                st.write("Validating and rendering pages")
                result = asyncio.run(
                    runtime.parse_document(
                        data=uploaded_data,
                        filename=filename,
                        model=MODEL_LABELS[selected_label],
                        ai_model=selected_ai_model.model_id,
                        api_key=api_key,
                        openai_base_url=openai_base_url,
                    )
                )
                st.write("Building annotated evidence PDF")
                try:
                    st.session_state.annotated_pdf = build_annotated_pdf(
                        source=uploaded_data,
                        filename=filename,
                        response=result,
                    )
                    st.session_state.artifact_error = None
                except Exception:
                    st.session_state.annotated_pdf = None
                    st.session_state.artifact_error = (
                        "The parse completed, but the annotated PDF could not be generated."
                    )
                st.session_state.result = result
                st.session_state.result_filename = filename
                status.update(label="Parsing complete", state="complete", expanded=False)
        except (DocumentInputError, OpenAIRequestError, ValueError) as exc:
            st.session_state.error_message = str(exc)
        except Exception:
            st.session_state.error_message = "Parsing failed unexpectedly. Check the local logs."

    if st.session_state.error_message:
        result_slot.error(st.session_state.error_message, icon=":material/error:")

    result = st.session_state.result
    if isinstance(result, ParseResponse):
        with result_slot:
            st.subheader(st.session_state.result_filename or "Result")
            ai_model = (
                DOCUMENT_MODEL_BY_ID.get(result.metadata.ai_model)
                if result.metadata.ai_model
                else None
            )
            cost = (
                estimate_model_cost(
                    ai_model.model_id,
                    input_tokens=result.metadata.input_tokens,
                    output_tokens=result.metadata.output_tokens,
                    cached_input_tokens=result.metadata.cached_input_tokens,
                )
                if ai_model is not None
                else None
            )
            metrics = st.columns(5)
            metrics[0].metric("Pages", result.metadata.page_count)
            metrics[1].metric("Blocks", _count_blocks(result.structure))
            metrics[2].metric("Engine", result.metadata.engine.replace("_", " ").title())
            metrics[3].metric("Duration", f"{result.metadata.duration_ms or 0} ms")
            metrics[4].metric(
                "Estimated cost",
                _format_cost_usd(cost.total_cost_usd) if cost is not None else "Unavailable",
            )
            st.caption(
                f"{result.metadata.output_characters:,} characters · "
                f"{result.metadata.source_format.upper()} source · "
                f"{result.metadata.input_tokens:,} input tokens · "
                f"{result.metadata.output_tokens:,} output tokens"
            )
            for warning in result.metadata.warnings:
                if warning == "figure_description_unavailable":
                    st.warning(
                        "One or more figures use a placeholder because a description was unavailable."
                    )
                else:
                    st.warning(warning)

            if ai_model is not None and cost is not None:
                with st.expander("Cost calculation"):
                    st.write(f"**{ai_model.label}** (`{ai_model.model_id}`)")
                    st.write(
                        f"Input: {_format_cost_usd(cost.input_cost_usd)} at "
                        f"${ai_model.input_price_per_million}/1M tokens"
                    )
                    if result.metadata.cached_input_tokens:
                        cached_rate = (
                            ai_model.cached_input_price_per_million
                            or ai_model.input_price_per_million
                        )
                        st.caption(
                            f"Includes {result.metadata.cached_input_tokens:,} cached input "
                            f"tokens at ${cached_rate}/1M."
                        )
                    st.write(
                        f"Output: {_format_cost_usd(cost.output_cost_usd)} at "
                        f"${ai_model.output_price_per_million}/1M tokens"
                    )
                    st.caption(
                        f"Estimate only. {ai_model.pricing_note} Provider invoices remain "
                        "authoritative."
                    )

            output_tab, pdf_tab, markdown_tab, json_tab = st.tabs(
                ["Output", "Annotated PDF", "Markdown", "JSON"],
                key="result_view",
                on_change="rerun",
            )
            if output_tab.open:
                with output_tab:
                    st.markdown(
                        _safe_rendered_markdown(result.markdown),
                        unsafe_allow_html=True,
                    )
            if pdf_tab.open:
                with pdf_tab:
                    artifact = st.session_state.annotated_pdf
                    if isinstance(artifact, AnnotatedPdfArtifact):
                        if artifact.kind == "source_overlay":
                            st.caption(
                                f"{artifact.annotated_blocks} grounded blocks are overlaid on the "
                                "source pages."
                            )
                        else:
                            st.caption(
                                "This source has no trustworthy page geometry. The PDF lists "
                                "semantic-only blocks without invented coordinates."
                            )
                        st.pdf(artifact.data, height=720, key="annotated_pdf_viewer")
                    elif st.session_state.artifact_error:
                        st.error(st.session_state.artifact_error)
                    else:
                        st.info("No annotated PDF is available for this result.")
            if markdown_tab.open:
                with markdown_tab:
                    st.code(result.markdown, language="markdown", wrap_lines=True)
            if json_tab.open:
                with json_tab:
                    st.json(result.model_dump(mode="json"), expanded=2)

            result_json = json.dumps(result.model_dump(mode="json"), indent=2)
            stem = Path(st.session_state.result_filename or "document").stem
            with st.container(horizontal=True):
                st.download_button(
                    "Download Markdown",
                    result.markdown,
                    file_name=f"{stem}.md",
                    mime="text/markdown",
                    icon=":material/download:",
                )
                artifact = st.session_state.annotated_pdf
                if isinstance(artifact, AnnotatedPdfArtifact):
                    st.download_button(
                        "Download annotated PDF",
                        artifact.data,
                        file_name=f"{stem}.annotated.pdf",
                        mime="application/pdf",
                        icon=":material/picture_as_pdf:",
                    )
                st.download_button(
                    "Download JSON",
                    result_json,
                    file_name=f"{stem}.json",
                    mime="application/json",
                    icon=":material/download:",
                )

with preview_column, st.container(border=True):
    st.subheader("Document preview")
    if uploaded is None or uploaded_data is None:
        st.info(
            "Choose a PDF, image, Office document, OpenDocument file, or CSV to begin.",
            icon=":material/upload_file:",
        )
    elif Path(uploaded.name).suffix.casefold() == ".pdf":
        st.pdf(uploaded_data, height=760)
    elif Path(uploaded.name).suffix.casefold() in IMAGE_EXTENSIONS:
        st.image(uploaded_data, caption=Path(uploaded.name).name, width="stretch")
    else:
        st.info(
            f"{Path(uploaded.name).name} is ready. Office and spreadsheet previews appear in the "
            "generated Markdown after parsing.",
            icon=":material/draft:",
        )

st.caption(f"Paperplane v{APP_VERSION} · Results remain only in this browser session.")
