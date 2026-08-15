# Security

Report vulnerabilities through the repository's private GitHub vulnerability-reporting
form. Do not open a public issue for an unpatched vulnerability and never include a real
document, provider response, or credential unless a maintainer explicitly requests a safe
reproduction through the private report.

## Supported surface

Paperplane v5 is a localhost-only Streamlit application. It has no public HTTP API,
authentication system, remote database, or external worker.

## Operator responsibility

Paperplane is self-hosted software, not a hosted document service. Operators are
responsible for the files they process, their authority to process them, the selected
local or cloud path, provider terms and data practices, API usage charges, output review,
and applicable privacy, copyright, contractual, and regulatory requirements.

The project maintainers do not receive user documents or credentials through Paperplane.
Cloud AI and optional cloud enhancement send selected page content to the chosen provider;
Docling, PDF Inspector, and loopback Ollama processing remain local.

Operators must:

- keep `OPENAI_API_KEY`, `XAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, and
  `AGNES_API_KEY` in user/process environment variables, an ignored `.env`, or ignored
  Streamlit secrets, in that precedence order; `OPENAI_BASE_URL` is an optional
  OpenAI-only override;
- use `GEMINI_API_KEY` only as a legacy fallback; `GOOGLE_API_KEY` takes precedence;
- run the app on `127.0.0.1`;
- review sensitive document handling before sending scans, images, or figure crops to the
  selected model provider endpoint;
- use the local Docling path for supported native documents when external inference is not desired;
- protect `%LOCALAPPDATA%\Paperplane`, where private job artifacts remain for seven days;
- keep dependencies locked and updated;
- use **Jobs** or **Stop and clear** to remove retained local data when required.

Uploaded files are processed in memory; job metadata and generated artifacts are retained
locally for seven days. The launcher imports user-level variables without printing or
persisting their values. The committed `.env.example` contains placeholders only.
