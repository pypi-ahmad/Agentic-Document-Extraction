# Security review: Paperplane v4

## Result

The v4 runtime has a small local attack surface: Streamlit, document parsing, and outbound
OpenAI requests. The previous API authentication, CORS, rate-limit, database, worker,
container, and JavaScript surfaces no longer exist.

## Controls present

- localhost-only Streamlit binding
- environment-first credentials with ignored `.env` and Streamlit secret fallbacks
- a committed `.env.example` containing placeholders only
- bounded upload size, page count, image pixels, and render area
- strict file inspection before model work
- strict structured-output schemas and grounding validation
- safe user-facing errors without provider payloads or keys
- no application persistence or cross-session result cache
- locked dependencies and automated dependency review

## Operational requirements

- Do not expose the port publicly.
- Treat scans, images, and extracted figure crops as data sent to the configured OpenAI endpoint;
  native Docling text conversion remains local.
- Treat downloaded annotated PDFs as derived sensitive data; Paperplane otherwise keeps them
  only in session memory.
- Rotate a key immediately if it is ever committed or displayed.
- Review grounded output before high-impact use.
- Keep `uv.lock` and CI green before release.
