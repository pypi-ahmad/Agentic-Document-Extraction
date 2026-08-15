"""Paperplane multipage Streamlit entrypoint."""

import streamlit as st

from paperplane import shutdown

st.set_page_config(
    page_title="Paperplane",
    page_icon=":material/description:",
    layout="wide",
)

navigation = st.navigation(
    [
        st.Page(
            "streamlit_app.py", title="Parse", icon=":material/document_scanner:", default=True
        ),
        st.Page("app_pages/organize.py", title="Organize", icon=":material/account_tree:"),
        st.Page("app_pages/jobs.py", title="Jobs", icon=":material/work_history:"),
        st.Page("app_pages/cost.py", title="Cost", icon=":material/payments:"),
    ]
)

st.session_state.setdefault("session_usage", {})


def _stop_and_clear() -> None:
    st.cache_data.clear()
    st.cache_resource.clear()
    st.session_state.clear()
    st.session_state.shutdown_pending = True
    shutdown.schedule_process_exit()


@st.dialog("Stop and clear Paperplane?", icon=":material/power_settings_new:")
def _confirm_shutdown() -> None:
    if st.session_state.get("shutdown_pending", False):
        st.html(shutdown.SHUTDOWN_HTML, unsafe_allow_javascript=True)
        st.stop()
    st.write("This stops active work and disconnects every open Paperplane tab.")
    st.caption("Downloaded models, job history, and saved artifacts are preserved.")
    with st.container(horizontal=True):
        if st.button("Cancel", width="stretch"):
            st.rerun()
        st.button(
            "Stop and clear now",
            type="primary",
            icon=":material/power_settings_new:",
            width="stretch",
            on_click=_stop_and_clear,
        )


st.html(shutdown.TAB_LISTENER_HTML, unsafe_allow_javascript=True)
with st.sidebar:
    st.divider()
    if st.button(
        "Stop and clear",
        icon=":material/power_settings_new:",
        type="tertiary",
        width="stretch",
    ):
        _confirm_shutdown()

navigation.run()
