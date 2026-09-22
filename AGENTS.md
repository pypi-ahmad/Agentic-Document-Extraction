<!-- code-review-graph MCP tools -->
# Paperplane project contract

Paperplane = local, no-DB Streamlit doc parser. Native content use Docling; scans/images/figure descriptions use AI model picked in UI. Catalog in `paperplane/model_catalog.py`, docs in `docs/MODELS.md`. Uploads/results session-only. Run on `127.0.0.1:8551`. Update docs with every code change.

## MCP Tools: code-review-graph

**IMPORTANT: Project has knowledge graph. ALWAYS use code-review-graph MCP tools BEFORE Grep/Glob/Read.** Graph faster, cheaper (fewer tokens), gives structural context (callers, dependents, test coverage) file scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes_tool` or `query_graph_tool` instead of Grep
- **Understanding impact**: `get_impact_radius_tool` instead of manually tracing imports
- **Code review**: `detect_changes_tool` + `get_review_context_tool` instead of reading entire files
- **Finding relationships**: `query_graph_tool` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview_tool` + `list_communities_tool`

Fall back to Grep/Glob/Read only when graph no cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes_tool` | Reviewing code changes: gives risk-scored analysis |
| `get_review_context_tool` | Need source snippets for review: token-efficient |
| `get_impact_radius_tool` | Understanding blast radius of a change |
| `get_affected_flows_tool` | Finding which execution paths are impacted |
| `query_graph_tool` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes_tool` | Finding functions/classes by name or keyword |
| `get_architecture_overview_tool` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. Graph auto-updates on file changes (via hooks).
2. Use `detect_changes_tool` for code review.
3. Use `get_affected_flows_tool` to understand impact.
4. Use `query_graph_tool` pattern="tests_for" to check coverage.


<!-- SHARED-ENGINEERING-POLICY:START -->
## Shared engineering policy

- Senior engineer. Ground decisions in repo instructions, code, tests, authoritative docs.
- Stay factual. Insufficient evidence → state what unknown, never guess. Surface consequential assumptions and competing interpretations.
- Non-trivial work: define observable success criteria + brief `step -> check` plan. Pause only for plan-only requests, material choices, or risky/irreversible actions.
- Small coherent increments. Verify one unit before next. Split changes before diff hard to review.
- Minimum sufficient implementation. No speculative features, one-use abstractions, unrequested configurability, or defensive branches without evidenced failure mode.
- Edits surgical, consistent with local style. No adjacent cleanup. Remove only artifacts made unused by current change.
- Run narrowest relevant verification. Report what passed, what not run, remaining risk.
- Production prompts: Role, Never Guess, Background, ordered Steps, locked Output contract. Parseable tags only when downstream tool needs them.
- Prefer deterministic workflow when decision tree known. Agent only when ambiguity, token cost, step capability, and failure observability justify it. High-stakes hard-to-detect failures stay read-only or human-reviewed.
- Persist correction only when user explicitly asks, using appropriate instruction file not another tool's command syntax.
<!-- SHARED-ENGINEERING-POLICY:END -->

<!-- okf:start -->
## Open Knowledge Format v0.2

Canonical governed project knowledge lives in `knowledge/index.md`.

- Read the index before architecture, policy, runbook, or domain work.
- Load only concepts relevant to the current task.
- Warn before relying on draft, deprecated, stale, or unverified concepts.
- Native instructions govern behavior; current source and tests govern factual conflicts.
<!-- okf:end -->
