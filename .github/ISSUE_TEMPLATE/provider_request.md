name: Vision model integration request
description: Request a new cloud document-vision model for Paperplane's fixed catalog.
title: "[integration] "
labels: ["enhancement", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Use this template to propose a provider-native vision adapter and
        catalog entry for scanned pages, images, and figure descriptions.

  - type: input
    id: name
    attributes:
      label: Provider name
      placeholder: "e.g. Mistral, Google Document AI, Surya OCR"
    validations:
      required: true

  - type: input
    id: model
    attributes:
      label: Exact production model ID
      description: Link to the provider's official model documentation.
      placeholder: "provider-model-id"
    validations:
      required: true

  - type: textarea
    id: capability
    attributes:
      label: What does it do?
      description: |
        Describe document-vision quality, image inputs, structured-output
        support, limits, pricing, and why the existing catalog is insufficient.

  - type: textarea
    id: integration
    attributes:
      label: Integration plan
      description: |
        Identify the official API endpoint and structured-output mechanism.
        Explain how usage tokens map into Paperplane's shared contract and
        whether the adapter needs a new dependency.

  - type: textarea
    id: env
    attributes:
      label: Configuration
      description: |
        Which credential environment variable is required? Include only its
        name, never a key value. Are any safe endpoint overrides necessary?

  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I searched existing issues and this is not a duplicate.
          required: true
        - label: I would be willing to open a PR for this.
