"""Paperplane multipage Streamlit entrypoint."""

import streamlit as st

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
        st.Page("app_pages/benchmarks.py", title="Benchmarks", icon=":material/analytics:"),
    ]
)
navigation.run()
