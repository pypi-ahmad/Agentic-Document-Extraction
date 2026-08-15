"""Classify, Split, and Section workflows."""

from __future__ import annotations

import json

import streamlit as st

from paperplane.ade_workflows import (
    ClassDefinition,
    classify_document,
    section_document,
    split_document,
)

st.title("Organize")
st.caption("Run cited document workflows over the selected Parse result.")

completed = [item for item in st.session_state.get("batch_outcomes", []) if item.result is not None]
if not completed:
    st.info("Parse at least one document first.", icon=":material/document_scanner:")
    st.stop()

if st.session_state.get("organize_document") not in [None, *completed]:
    del st.session_state["organize_document"]
selected = st.selectbox(
    "Parsed document",
    completed,
    format_func=lambda item: item.filename,
    key="organize_document",
    persist_state="session",
)
st.session_state.setdefault("organize_view", "Classify")


def save_organize_view() -> None:
    st.session_state.organize_view = st.session_state.organize_view_widget


classify_tab, split_tab, section_tab = st.tabs(
    ["Classify", "Split", "Section"],
    default=st.session_state.organize_view,
    key="organize_view_widget",
    on_change=save_organize_view,
)


def classes_from_text(value: str) -> list[ClassDefinition]:
    names = [item.strip() for item in value.splitlines() if item.strip()]
    return [ClassDefinition(name=name, description=name) for name in names]


with classify_tab:
    class_text = st.text_area(
        "Allowed classes",
        value="invoice\nletter\nreport",
        key="organize_classify_classes",
        persist_state="session",
    )
    if st.button("Classify pages"):
        try:
            st.session_state.classify_result = classify_document(
                selected.result, classes_from_text(class_text)
            )
        except ValueError as exc:
            st.error(str(exc))
    if result := st.session_state.get("classify_result"):
        st.json(result.model_dump(mode="json"))

with split_tab:
    split_text = st.text_area(
        "Split classes",
        value="invoice\nletter\nreport",
        key="organize_split_classes",
        persist_state="session",
    )
    if st.button("Split document"):
        try:
            st.session_state.split_result = split_document(
                selected.result, classes_from_text(split_text)
            )
        except ValueError as exc:
            st.error(str(exc))
    if result := st.session_state.get("split_result"):
        st.json(result.model_dump(mode="json"))

with section_tab:
    if st.button("Detect sections"):
        st.session_state.section_result = section_document(selected.result)
    if result := st.session_state.get("section_result"):
        st.json(result.model_dump(mode="json"))
        st.download_button(
            "Download section map",
            json.dumps(result.model_dump(mode="json"), indent=2),
            file_name="sections.json",
            mime="application/json",
        )
