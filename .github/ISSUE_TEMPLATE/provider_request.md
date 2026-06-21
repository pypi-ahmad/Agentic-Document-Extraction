name: Provider (OCR or LLM) request
description: Request a new parser/OCR or LLM provider.
title: "[provider] "
labels: ["enhancement", "provider", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Use this template for adding a new OCR/parser engine
        (`BaseOCRProvider`) or a new LLM provider
        (`BaseLLMProvider`).

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
        - OCR / parser
        - LLM
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
