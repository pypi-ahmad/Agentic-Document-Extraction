# Graph Report - .  (2026-08-14)

## Corpus Check
- Corpus is ~45,196 words - fits in a single context window. You may not need a graph.

## Summary
- 472 nodes · 1341 edges · 50 communities (22 shown, 28 thin omitted)
- Extraction: 79% EXTRACTED · 21% INFERRED · 0% AMBIGUOUS · INFERRED: 285 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Grounding and Processing Pipeline
- Processing Models and Tests
- Document Contracts and Assembly
- Annotated PDF and Conversion
- Handbook Generation
- Document Ingestion
- OpenAI API Integration
- Release Automation
- Parser Integration Tests
- Refactoring and Review Graph
- Processing Recipes
- Graph Exploration Guidance
- Historical Evidence Studio
- Hybrid Extraction Architecture
- Graph First Discovery
- Product Capability Documentation
- Historical Dark Theme
- Capability Guide Builder
- Contributor Verification Workflow
- Cursor Graph Configuration
- Legacy Architecture Migration
- Secure Local Launch
- Claude Graph Configuration
- Root Graph Configuration
- Qoder Graph Configuration
- Dependency Security Automation
- Issue Proposal Templates
- Local Deployment Scope
- Processing Performance Policy
- Shared Output Data Flow
- Output Quality Validation
- Session Start Hook
- Graph Update Hook
- Streamlit Migration Delivery
- Bug Report Template
- Pre Commit Gates
- Docling Input Expansion
- Community Conduct
- Contribution Scope
- Architecture Decisions
- Grounding Evidence Model
- System Architecture Diagram
- Release History
- GitHub Issue Configuration
- Project Metadata
- Source Release Process
- Sample Scanned Document
- Attack Surface Controls
- Sensitive Document Handling

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
- **Graph-First Agent Guidance** — agents_graph_first_code_discovery, claude_graph_first_code_discovery, codebuddy_graph_first_code_discovery, _kiro_steering_code_review_graph_graph_first_code_discovery [INFERRED 0.95]
- **Hybrid Document Extraction Pipeline** — onboarding_local_stateless_streamlit_application, docs_architecture_hybrid_document_routing, docs_engines_docling_native_engine, docs_engines_openai_vision_engine, docs_architecture_grounding_model [EXTRACTED 1.00]
- **Local Runtime Principles** — docs_run_app_windows_launcher, docs_how_it_works_shared_output, docs_adr_0004_secure_by_default_secure_local_boundary [INFERRED 0.85]
- **Streamlit v4 Transition** — tasks_plan_streamlit_only_migration, tasks_todo_v4_completion [EXTRACTED 1.00]
- **Historical Frontend Experience Design** — docs_superpowers_plans_2026_07_26_dark_theme_historical_plan, docs_superpowers_plans_2026_07_26_evidence_studio_historical_plan, docs_superpowers_specs_2026_07_26_evidence_studio_design_evidence_studio_design [EXTRACTED 1.00]

## Communities (50 total, 28 thin omitted)

### Community 0 - "Grounding and Processing Pipeline"
Cohesion: 0.07
Nodes (74): align_text_to_native_words(), map_crop_box_to_page(), _padded_box(), Deterministic rendering and coordinate transforms for V2 grounding., Return the exact union of a contiguous native-word match., render_crop(), RenderedCrop, _token() (+66 more)

### Community 1 - "Processing Models and Tests"
Cohesion: 0.13
Nodes (52): RenderedPage, OpenAIUsage, BaseModel, StructuredGeneration, GroundingMethod, ProcessingMode, VerificationStatus, V2PageProcessor (+44 more)

### Community 2 - "Document Contracts and Assembly"
Cohesion: 0.09
Nodes (52): DocItem, DoclingDocument, FigureDescriber, AgenticBlockInput, AgenticPageInput, _assemble_atomic_grounding(), assemble_parse_response(), AtomicGrounding (+44 more)

### Community 3 - "Annotated PDF and Conversion"
Cohesion: 0.07
Nodes (37): Document, DocumentConverter, AnnotatedPdfArtifact, build_annotated_pdf(), _content_nodes(), _new_report_page(), _pdf_text(), _plain_excerpt() (+29 more)

### Community 4 - "Handbook Generation"
Cohesion: 0.15
Nodes (16): BaseDocTemplate, ParagraphStyle, build(), main(), build_pdf(), _code_block(), HandbookTemplate, _inline() (+8 more)

### Community 5 - "Document Ingestion"
Cohesion: 0.20
Nodes (20): inspect_document(), InspectedDocument, _is_native_pdf_page(), _office_mime_type(), Page, Document validation, inspection, rendering, and native word extraction., render_page(), _image_bytes() (+12 more)

### Community 6 - "OpenAI API Integration"
Cohesion: 0.20
Nodes (15): AsyncClient, capture_audit_calls(), _emit_audit(), OpenAIDocumentAdapter, OpenAIRequestError, Any, OpenAI Responses API boundary for grounded document extraction., Capture sanitized request/response records for the current async context. (+7 more)

### Community 7 - "Release Automation"
Cohesion: 0.33
Nodes (9): Namespace, add_changelog(), command(), current_version(), main(), next_version(), parse_args(), Path (+1 more)

### Community 8 - "Parser Integration Tests"
Cohesion: 0.29
Nodes (6): PageResult, BaseModel, FakeProcessor, _png(), asyncio, test_parser_returns_one_grounded_response_without_persistence()

### Community 9 - "Refactoring and Review Graph"
Cohesion: 0.29
Nodes (7): Dependency-Aware Refactoring, Risk-Aware Code Review, Dependency-Aware Refactoring, Risk-Aware Code Review, Dependency-Aware Refactoring, Risk-Aware Code Review, Graph-First Exploration Policy

### Community 10 - "Processing Recipes"
Cohesion: 0.38
Nodes (6): processing_recipe(), ProcessingRecipe, BaseModel, RecipeVersion, Versioned processing recipes with an operator rollback path., VerificationBudget

### Community 11 - "Graph Exploration Guidance"
Cohesion: 0.33
Nodes (6): Knowledge Graph Debugging, Graph-Powered Codebase Exploration, Knowledge Graph Debugging, Graph-Powered Codebase Exploration, Knowledge Graph Debugging, Graph-Powered Codebase Exploration

### Community 12 - "Historical Evidence Studio"
Cohesion: 0.33
Nodes (6): Document-First Workspace, Evidence Studio Historical Plan, Artifact Preview, Evidence Studio Historical Design, Balanced Mode, Bounded Vision Work

### Community 13 - "Hybrid Extraction Architecture"
Cohesion: 0.40
Nodes (5): Hybrid Document Routing, Docling Native Engine, OpenAI Vision Engine, Local Stateless Streamlit Application, Local Document Extraction Architecture

### Community 14 - "Graph First Discovery"
Cohesion: 0.50
Nodes (4): Graph-First Code Discovery, Graph-First Code Discovery, Graph-First Code Discovery, Graph-First Code Discovery

### Community 15 - "Product Capability Documentation"
Cohesion: 0.50
Nodes (4): Document Capability Contract, Document Capability Contract, User Operating Guidance, Paperplane Product Overview

### Community 16 - "Historical Dark Theme"
Cohesion: 0.50
Nodes (4): Dark Theme Historical Plan, Persisted Theme Toggle, Dark Theme Historical Design, Theme Storage Failure Handling

### Community 17 - "Capability Guide Builder"
Cohesion: 0.50
Nodes (3): build(), Build the reader-friendly HTML capability guide from its Markdown source., Render the Markdown source with navigation and accessible page chrome.

### Community 18 - "Contributor Verification Workflow"
Cohesion: 0.67
Nodes (3): Continuous Verification Workflow, Engineering Workflow, Contributor Learning Path

### Community 20 - "Legacy Architecture Migration"
Cohesion: 0.67
Nodes (3): Archived LangGraph Decision, v4 Simplification, Archived Hosted Operations

### Community 21 - "Secure Local Launch"
Cohesion: 0.67
Nodes (3): Secure Local Boundary, Windows Launcher, Credential Precedence

## Knowledge Gaps
- **46 isolated node(s):** `uvx`, `crg-session-start.sh script`, `crg-update.sh script`, `uvx`, `uvx` (+41 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BoundingBox` connect `Grounding and Processing Pipeline` to `Processing Models and Tests`, `Document Contracts and Assembly`, `Annotated PDF and Conversion`, `Document Ingestion`, `Parser Integration Tests`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `V2PageProcessor` connect `Processing Models and Tests` to `Grounding and Processing Pipeline`, `Document Contracts and Assembly`, `Annotated PDF and Conversion`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Why does `DocumentInputError` connect `Document Contracts and Assembly` to `Grounding and Processing Pipeline`, `Processing Models and Tests`, `Annotated PDF and Conversion`, `Document Ingestion`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 34 inferred relationships involving `BoundingBox` (e.g. with `RenderedCrop` and `DocumentInputError`) actually correct?**
  _`BoundingBox` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `V2PageProcessor` (e.g. with `AgenticDocumentParser` and `RenderedPage`) actually correct?**
  _`V2PageProcessor` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `RenderedPage` (e.g. with `BoundingBox` and `NativeWord`) actually correct?**
  _`RenderedPage` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `NativeWord` (e.g. with `RenderedCrop` and `DocumentInputError`) actually correct?**
  _`NativeWord` has 23 INFERRED edges - model-reasoned connections that need verification._