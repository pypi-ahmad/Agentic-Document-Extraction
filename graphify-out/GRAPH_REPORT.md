# Graph Report - .  (2026-08-14)

## Corpus Check
- Corpus is ~46,726 words - fits in a single context window. You may not need a graph.

## Summary
- 469 nodes · 1352 edges · 39 communities (19 shown, 20 thin omitted)
- Extraction: 79% EXTRACTED · 21% INFERRED · 0% AMBIGUOUS · INFERRED: 279 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Docling Parsing Contracts
- Pipeline Models and Policies
- V2 Processing Interfaces
- Grounding and Input Rendering
- Handbook PDF Generation
- Annotated Evidence PDF
- OpenAI Document Adapter
- Architecture and Output Rationale
- Release Versioning Automation
- Bounded Parser Tests
- Graph-Aware Refactoring
- Graph Debugging and Exploration
- Extraction Engine Architecture
- Streamlit Extraction Paths
- HTML Guide Builder
- MCP Graph Configuration
- Local Deployment Security
- Windows Setup and Recovery
- MCP Graph Configuration
- MCP Graph Configuration
- MCP Graph Configuration
- Paperplane Session Routing
- Dependency Security Automation
- Feature Request Templates
- Continuous Quality Gates
- Safe Contribution Practice
- Grounded Output Formats
- Result Visualization Views
- Output Contract Validation
- PDF Latency Design
- Dark Theme Design
- Evidence Studio Design
- Session Start Hook
- Graph Update Hook
- Streamlit Migration Plan
- Bug Reporting
- Architecture Decision Records
- Application Package

## God Nodes (most connected - your core abstractions)
1. `BoundingBox` - 78 edges
2. `V2PageProcessor` - 61 edges
3. `RenderedPage` - 53 edges
4. `NativeWord` - 35 edges
5. `ProcessingMode` - 34 edges
6. `VerificationStatus` - 32 edges
7. `OpenAIUsage` - 29 edges
8. `StructuredGeneration` - 29 edges
9. `GroundingMethod` - 28 edges
10. `_png()` - 22 edges

## Surprising Connections (you probably didn't know these)
- `Knowledge Graph Debugging` --semantically_similar_to--> `Knowledge Graph Debugging`  [INFERRED] [semantically similar]
  .codebuddy/skills/debug-issue/SKILL.md → .claude/skills/debug-issue/SKILL.md
- `Knowledge Graph Debugging` --semantically_similar_to--> `Knowledge Graph Debugging`  [INFERRED] [semantically similar]
  .gemini/skills/debug-issue/SKILL.md → .claude/skills/debug-issue/SKILL.md
- `Graph-Powered Codebase Exploration` --semantically_similar_to--> `Graph-Powered Codebase Exploration`  [INFERRED] [semantically similar]
  .codebuddy/skills/explore-codebase/SKILL.md → .claude/skills/explore-codebase/SKILL.md
- `Graph-Powered Codebase Exploration` --semantically_similar_to--> `Graph-Powered Codebase Exploration`  [INFERRED] [semantically similar]
  .gemini/skills/explore-codebase/SKILL.md → .claude/skills/explore-codebase/SKILL.md
- `Dependency-Aware Refactoring` --semantically_similar_to--> `Dependency-Aware Refactoring`  [INFERRED] [semantically similar]
  .codebuddy/skills/refactor-safely/SKILL.md → .claude/skills/refactor-safely/SKILL.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Graph-Powered Engineering Workflow** — _claude_skills_debug_issue_skill_knowledge_graph_debugging, _claude_skills_explore_codebase_skill_graph_powered_exploration, _claude_skills_refactor_safely_skill_dependency_aware_refactoring, _claude_skills_review_changes_skill_risk_aware_code_review [EXTRACTED 1.00]
- **Automated Quality and Security Controls** — _github_workflows_ci_yml_continuous_verification, _github_workflows_dependency_review_yml_dependency_security_review, _github_dependabot_yml_dependency_update_automation, _pre_commit_config_pre_commit_quality_gates [INFERRED 0.85]
- **Dual Engine Document Processing** — docs_architecture_docling_path, docs_architecture_openai_vision_path, docs_architecture_shared_assembler [EXTRACTED 1.00]
- **Local Stateless Operating Boundary** — readme_session_only_state, docs_limitations_local_single_user, docs_deployment_localhost_only [INFERRED 0.95]
- **Paperplane v4.1 Extraction Workflow** — docs_how_it_works_automatic_routing, docs_how_it_works_grounded_output, docs_architecture_paperplane_system_evidence_pdf [EXTRACTED 1.00]
- **Streamlit v4 Transition** — tasks_plan_streamlit_only_migration, tasks_todo_v4_completion, docs_release_notes_paperplane_v41 [EXTRACTED 1.00]
- **Historical Frontend Plans** — docs_superpowers_plans_dark_theme, docs_superpowers_plans_evidence_studio, docs_architecture_paperplane_system_v41 [EXTRACTED 1.00]

## Communities (39 total, 20 thin omitted)

### Community 0 - "Docling Parsing Contracts"
Cohesion: 0.06
Nodes (67): DocItem, DoclingDocument, DocumentConverter, FigureDescriber, AgenticBlockInput, AgenticPageInput, _assemble_atomic_grounding(), assemble_parse_response() (+59 more)

### Community 1 - "Pipeline Models and Policies"
Cohesion: 0.07
Nodes (68): _best_fallback_content(), _cache_key(), AtomicLine, GroundedChunk, Grounding, mode_policy(), ModePolicy, BaseModel (+60 more)

### Community 2 - "V2 Processing Interfaces"
Cohesion: 0.12
Nodes (54): RenderedPage, OpenAIUsage, BaseModel, StructuredGeneration, GroundingMethod, ProcessingMode, VerificationStatus, StructuredAdapter (+46 more)

### Community 3 - "Grounding and Input Rendering"
Cohesion: 0.11
Nodes (33): align_text_to_native_words(), map_crop_box_to_page(), _padded_box(), Deterministic rendering and coordinate transforms for V2 grounding., Return the exact union of a contiguous native-word match., render_crop(), RenderedCrop, _token() (+25 more)

### Community 4 - "Handbook PDF Generation"
Cohesion: 0.15
Nodes (16): BaseDocTemplate, ParagraphStyle, build(), main(), build_pdf(), _code_block(), HandbookTemplate, _inline() (+8 more)

### Community 5 - "Annotated Evidence PDF"
Cohesion: 0.17
Nodes (19): Document, AnnotatedPdfArtifact, build_annotated_pdf(), _content_nodes(), _new_report_page(), _pdf_text(), _plain_excerpt(), _populate_semantic_report() (+11 more)

### Community 6 - "OpenAI Document Adapter"
Cohesion: 0.20
Nodes (15): AsyncClient, capture_audit_calls(), _emit_audit(), OpenAIDocumentAdapter, OpenAIRequestError, Any, OpenAI Responses API boundary for grounded document extraction., Capture sanitized request/response records for the current async context. (+7 more)

### Community 7 - "Architecture and Output Rationale"
Cohesion: 0.18
Nodes (14): Bounded Page Processing, Secure-by-Default Boundary, In-Memory Evidence PDF, Paperplane v4.1 System Architecture, Automatic Document Routing, Grounded Output Contract, Local Docling Conversion, OpenAI Vision Parsing (+6 more)

### Community 8 - "Release Versioning Automation"
Cohesion: 0.33
Nodes (9): Namespace, add_changelog(), command(), current_version(), main(), next_version(), parse_args(), Path (+1 more)

### Community 9 - "Bounded Parser Tests"
Cohesion: 0.29
Nodes (6): PageResult, BaseModel, FakeProcessor, _png(), asyncio, test_parser_returns_one_grounded_response_without_persistence()

### Community 10 - "Graph-Aware Refactoring"
Cohesion: 0.29
Nodes (7): Dependency-Aware Refactoring, Risk-Aware Code Review, Dependency-Aware Refactoring, Risk-Aware Code Review, Dependency-Aware Refactoring, Risk-Aware Code Review, Graph-First Exploration Policy

### Community 11 - "Graph Debugging and Exploration"
Cohesion: 0.33
Nodes (6): Knowledge Graph Debugging, Graph-Powered Codebase Exploration, Knowledge Graph Debugging, Graph-Powered Codebase Exploration, Knowledge Graph Debugging, Graph-Powered Codebase Exploration

### Community 12 - "Extraction Engine Architecture"
Cohesion: 0.40
Nodes (5): v4.1 Docling Input Expansion, Docling Engine, OpenAI Vision Engine, Source-Only Release Process, Sensitive Document Handling

### Community 13 - "Streamlit Extraction Paths"
Cohesion: 0.50
Nodes (5): Docling Native-Document Path, OpenAI Vision Path, Shared Markdown and JSON Assembler, Streamlit Workspace, Semantic-Only Geometry

### Community 14 - "HTML Guide Builder"
Cohesion: 0.50
Nodes (3): build(), Build the reader-friendly HTML capability guide from its Markdown source., Render the Markdown source with navigation and accessible page chrome.

### Community 16 - "Local Deployment Security"
Cohesion: 0.67
Nodes (3): Localhost-Only Deployment, Local Single-User Boundary, v4 Simplification

### Community 17 - "Windows Setup and Recovery"
Cohesion: 0.67
Nodes (3): Paperplane Windows Launcher, Operational Recovery Runbook, Environment Credential Setup

### Community 21 - "Paperplane Session Routing"
Cohesion: 0.67
Nodes (3): Automatic Per-Page Routing, Paperplane, Session-Only State

## Knowledge Gaps
- **39 isolated node(s):** `uvx`, `crg-session-start.sh script`, `crg-update.sh script`, `uvx`, `uvx` (+34 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BoundingBox` connect `Pipeline Models and Policies` to `Bounded Parser Tests`, `V2 Processing Interfaces`, `Grounding and Input Rendering`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Why does `V2PageProcessor` connect `V2 Processing Interfaces` to `Docling Parsing Contracts`, `Pipeline Models and Policies`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `DocumentInputError` connect `Grounding and Input Rendering` to `Docling Parsing Contracts`, `Pipeline Models and Policies`, `V2 Processing Interfaces`, `Annotated Evidence PDF`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 34 inferred relationships involving `BoundingBox` (e.g. with `RenderedCrop` and `DocumentInputError`) actually correct?**
  _`BoundingBox` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `V2PageProcessor` (e.g. with `AgenticDocumentParser` and `RenderedPage`) actually correct?**
  _`V2PageProcessor` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `RenderedPage` (e.g. with `BoundingBox` and `NativeWord`) actually correct?**
  _`RenderedPage` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `NativeWord` (e.g. with `RenderedCrop` and `DocumentInputError`) actually correct?**
  _`NativeWord` has 23 INFERRED edges - model-reasoned connections that need verification._