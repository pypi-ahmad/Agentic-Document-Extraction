# Paperplane v4 implementation plan

Paperplane v4 replaces the previous multi-stack application with one local Streamlit process.
The UI calls the framework-neutral `paperplane` parser directly. Only the current upload and
result live in Streamlit session memory.

Completed work:

- migrate active parser modules into `paperplane/`;
- add `streamlit_app.py` and the local Streamlit configuration;
- add a six-model AI selector with provider-native adapters;
- load provider credentials from Windows user environment variables;
- remove the REST API, JavaScript frontend, Docker, packaging, extraction, and legacy modules;
- simplify launch, CI, dependencies, releases, and documentation;
- verify parser behavior and the Streamlit workflow.
