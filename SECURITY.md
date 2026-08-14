# Security

Report vulnerabilities privately through GitHub Security Advisories. Do not open a public
issue for an unpatched vulnerability.

## Supported surface

Paperplane v4 is a localhost-only Streamlit application. It has no public HTTP API,
authentication system, database, worker, or durable upload store.

Operators must:

- keep `OPENAI_API_KEY` in user/process environment variables, an ignored `.env`, or
  ignored Streamlit secrets, in that precedence order;
- run the app on `127.0.0.1`;
- review sensitive document handling before sending scans, images, or figure crops to OpenAI;
- use the local Docling path for supported native documents when external inference is not desired;
- keep annotated PDFs session-only unless the user explicitly downloads them;
- keep dependencies locked and updated;
- stop the process to clear all server-side sessions.

Uploaded files and model results are held in memory for the current Streamlit session only.
The launcher imports user-level variables without printing or persisting their values. The
committed `.env.example` contains placeholders only.
