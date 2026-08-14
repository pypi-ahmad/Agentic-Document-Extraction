name: Feature request
description: Suggest a new feature, engine, or pipeline stage.
title: "[feat] "
labels: ["enhancement", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Use this template for new inputs, output-contract changes,
        processing behavior, evidence views, or other user-visible changes.

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
        Describe the user-visible behavior, parser stage, Streamlit workflow,
        or downloaded artifact that would change.
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
        Who benefits? Does it change a supported input, the Markdown/JSON
        contract, provider usage, a UI view, or an artifact?

  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I searched existing issues and this is not a duplicate.
          required: true
        - label: I would be willing to open a PR for this.
