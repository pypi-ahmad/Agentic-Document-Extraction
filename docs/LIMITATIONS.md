# Limitations

## Product scope

- Local, single-user operation only
- No public API, batch endpoint, background jobs, cancellation, or resume
- No durable history, upload storage, result storage, or application database
- No schema extraction or reusable extraction contracts
- No authentication or multi-user isolation beyond separate Streamlit sessions
- No Docker image, hosted deployment profile, or PyPI package

## Input and runtime limits

- Maximum upload: 200 MB
- Maximum document: 500 pages or image frames
- Maximum PDF page canvas area: 4,000,000 source-coordinate units
- Maximum decoded image content: 40,000,000 pixels across frames
- Synchronous processing and sequential vision pages
- Legacy DOC/PPT/XLS, RTF, encrypted PDFs, and password-protected files unsupported
- Local Docling conversion does not OCR scans; vision input requires the selected model's
  credential listed in [MODELS.md](MODELS.md)

## Evidence limits

- Extraction quality depends on source quality and model behavior
- IDs are stable within one response, not guaranteed across re-parses
- Office elements without physical geometry are `semantic_only` with null boxes
- Figure descriptions can be unavailable when the selected model is unconfigured or fails
- Scans, images, and requested figure crops are sent to the selected provider endpoint
- Annotated PDFs are review aids, not independent proof of correctness

Always review extracted values and source evidence before financial, legal, medical,
safety, or other high-impact use.
