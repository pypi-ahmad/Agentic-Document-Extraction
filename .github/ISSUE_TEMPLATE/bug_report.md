name: Bug report
description: Report a bug or unexpected behaviour.
title: "[bug] "
labels: ["bug", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to file a bug. Please fill in every
        section below so we can reproduce and fix it quickly.

  - type: input
    id: version
    attributes:
      label: Affected version
      description: "Run `curl -s localhost:8000/info` and paste the `version` field."
      placeholder: "0.2.0"
    validations:
      required: true

  - type: textarea
    id: summary
    attributes:
      label: Summary
      description: One or two sentences.
    validations:
      required: true

  - type: textarea
    id: repro
    attributes:
      label: Steps to reproduce
      description: |
        Minimal steps that trigger the bug. Include the document
        type (PDF/PNG/JPEG/TIFF), the parser engine (auto / paddleocr
        / glmocr / pymupdf), the LLM provider, and the schema fields
        if relevant.
      placeholder: |
        1. Upload `invoice.png` (1.2 MB, 1 page).
        2. Pick the Invoice preset, click Extract.
        3. ...
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected behaviour
    validations:
      required: true

  - type: textarea
    id: actual
    attributes:
      label: Actual behaviour
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: Relevant logs / error output
      description: |
        Copy from the backend log (or the response body of
        `GET /api/extractions/{id}`). Sanitise any API keys.

  - type: textarea
    id: env
    attributes:
      label: Environment
      description: |
        OS, Python version (`python -V`), `uv --version`, whether
        Ollama / PaddleOCR are installed, any custom env vars.

  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I searched existing issues and this is not a duplicate.
          required: true
        - label: I can reproduce the bug on `main` at the version above.
          required: true
