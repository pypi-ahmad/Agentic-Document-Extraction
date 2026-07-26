name: Recognition or review integration request
description: Request a local or cloud recognition/review integration.
title: "[integration] "
labels: ["enhancement", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Use this template for a local recognition, cloud review, or
        schema-extraction integration.

  - type: input
    id: name
    attributes:
      label: Provider name
      placeholder: "e.g. Mistral, Google Document AI, Surya OCR"
    validations:
      required: true

  - type: dropdown
    id: kind
    attributes:
      label: Provider kind
      options:
        - Local recognition
        - Cloud review
        - Schema extraction
    validations:
      required: true

  - type: textarea
    id: capability
    attributes:
      label: What does it do?
      description: |
        One paragraph on what the provider does, the file types it
        supports (for OCR), and any model-listing behaviour it has.

  - type: textarea
    id: integration
    attributes:
      label: Integration plan
      description: |
        Which library / SDK? How would the provider class look? Does
        it need a new feature flag? Does it depend on a system
        install (e.g. ONNX, Tesseract)?

  - type: textarea
    id: env
    attributes:
      label: Configuration
      description: |
        Which env vars would the provider read? Defaults?

  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I searched existing issues and this is not a duplicate.
          required: true
        - label: I would be willing to open a PR for this.
