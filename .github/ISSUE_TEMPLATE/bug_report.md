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
      description: "Copy the Paperplane version shown in the Streamlit footer."
      placeholder: "4.2.1"
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
        type, selected AI model, processing mode, and whether the affected
        PDF pages are native, scanned, or mixed.
      placeholder: |
        1. Select GPT-5.6 Luna and Balanced mode.
        2. Upload `invoice.png` (1.2 MB, 1 page).
        3. Choose Parse document.
        4. ...
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
        Copy the safe UI error and relevant launcher/terminal output.
        Remove document content, provider responses, and API keys.

  - type: textarea
    id: env
    attributes:
      label: Environment
      description: |
        OS, Python version (`uv run python -V`), `uv --version`, selected
        model and mode, input type, and configured environment-variable
        names. Never include their values.

  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I searched existing issues and this is not a duplicate.
          required: true
        - label: I can reproduce the bug on `main` at the version above.
          required: true
