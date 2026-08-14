# Processing engines

The active parser uses three components:

| Component | Responsibility |
|---|---|
| PyMuPDF | Validate, render, crop, and recover native text coordinates |
| `gpt-5.6-luna` | Produce the structured page draft |
| `gpt-5.6-terra` | Verify ambiguous pages and crops within a bounded budget |

The public model aliases select policy, not different response contracts: Fast minimizes
verification, Balanced verifies flagged evidence, and Audit uses the largest inspection
budget.

Legacy local-engine modules remain internal compatibility code and are not mounted by the
active application. New integrations should target `/v2/parse` and its output contract.
