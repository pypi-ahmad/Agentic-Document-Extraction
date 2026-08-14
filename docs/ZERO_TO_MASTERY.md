# Paperplane from zero to mastery

## Mental model

Paperplane is a synchronous transformation:

```text
document bytes + model mode -> grounded document response
```

FastAPI validates the request. PyMuPDF renders pages. Luna drafts structured content.
Deterministic checks ground it to page coordinates. Terra verifies bounded ambiguous areas.
The assembler returns Markdown and JSON.

## Trace the code

1. Start at `backend/app/routers/dpt_api.py::parse_document`.
2. Follow `AgenticDocumentParser.parse` in `services/agentic/parsing.py`.
3. Inspect `V2PageProcessor.process_page` in `services/parsing/v2_pipeline.py`.
4. Read the output types in `services/agentic/contracts.py`.
5. Follow the browser call in `frontend/src/lib/api.ts` and rendering in
   `frontend/src/app/page.tsx`.

## Exercises

- Parse one native PDF and one scanned image; compare grounding methods.
- Run the same input in Fast, Balanced, and Audit modes; compare warnings and usage.
- Trace one Markdown block back to its page and bounding box.
- Add a contract test before changing any public response field.
- Simulate an upstream failure and confirm the API returns a safe error without credentials.

Mastery means you can explain every step between upload bytes and a grounded output block,
including where validation, model judgment, deterministic evidence, and abstention occur.
