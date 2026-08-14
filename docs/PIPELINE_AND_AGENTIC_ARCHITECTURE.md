# Pipeline and agentic architecture

Paperplane uses a bounded visual-document pipeline, not an autonomous open-ended agent:

```text
validate -> render -> Luna structured draft -> geometry gates
         -> optional Terra verification -> assemble response
```

The page processor records explicit provenance and abstains when evidence is insufficient.
Mode-specific verification budgets cap retries and model calls. Each HTTP request owns all
intermediate state and returns the completed document contract directly.

See [Architecture](ARCHITECTURE.md) for component boundaries and
[How it works](how-it-works.md) for the request lifecycle.
