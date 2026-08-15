"""Durable job history and artifact controls."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from paperplane.jobs import JobStore


def job_store() -> JobStore:
    local_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    root = local_root / "Paperplane"
    return JobStore(root / "paperplane.sqlite3", root / "artifacts", ttl_days=7)


st.title("Jobs")
st.caption("Job metadata and private artifacts are retained locally for seven days.")
store = job_store()
store.purge_expired()

jobs = store.list_jobs()
if not jobs:
    st.info("No retained jobs.")
else:
    st.dataframe(
        [
            {
                "Job": job.id,
                "File": job.filename,
                "Engine": job.engine,
                "Pages": f"{job.page_start}-{job.page_end or 'end'}",
                "Status": job.status,
                "Updated": job.updated_at,
            }
            for job in jobs
        ],
        hide_index=True,
    )
    jobs_by_id = {job.id: job for job in jobs}
    if st.session_state.get("jobs_selected_id") not in {None, *jobs_by_id}:
        del st.session_state["jobs_selected_id"]
    selected_id = st.selectbox(
        "Job",
        list(jobs_by_id),
        format_func=lambda job_id: f"{jobs_by_id[job_id].filename} · {jobs_by_id[job_id].status}",
        key="jobs_selected_id",
        persist_state="session",
    )
    selected = jobs_by_id[selected_id]
    if selected.status in {"pending", "running"} and st.button("Cancel selected job"):
        store.cancel_job(selected.id)
        st.rerun()
    if st.button("Delete selected job"):
        store.delete_job(selected.id)
        st.rerun()
    if st.button("Clear all retained jobs", type="secondary"):
        store.clear_all()
        st.rerun()
