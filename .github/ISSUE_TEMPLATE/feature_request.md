name: Feature request
description: Suggest a new feature, engine, or pipeline stage.
title: "[feat] "
labels: ["enhancement", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Use this template for new engines, new pipeline stages, new
        schema field types, new review actions, or anything else that
        changes user-visible behaviour.

  - type: textarea
    id: problem
    attributes:
      label: Problem
      description: |
        What user-facing problem does this solve? Why is the current
        behaviour insufficient?
    validations:
      required: true

  - type: textarea
    id: proposal
    attributes:
      label: Proposed solution
      description: |
        Describe the change in concrete terms. If it touches the
        engine registry, name the new module and the
        `BaseOCRProvider` / `BaseLLMProvider` subclass.
    validations:
      required: true

  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives considered
      description: |
        What else did you look at, and why is this the better path?

  - type: textarea
    id: impact
    attributes:
      label: Impact
      description: |
        Who benefits? Does it need a new config flag, a new schema
        field, a new API endpoint, a UI change?

  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I searched existing issues and this is not a duplicate.
          required: true
        - label: I would be willing to open a PR for this.
