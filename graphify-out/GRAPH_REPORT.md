# Graph Report - D:\AI\Github\Agentic-Document-Extraction  (2026-08-15)

## Corpus Check
- 168 files · ~82,303 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1028 nodes · 2855 edges · 95 communities (43 shown, 52 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 513 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- AI Provider Adapters
- Document Contracts and Docling
- Grounding and Geometry
- Runtime Model Integration
- Ollama OCR Pipeline
- Document Ingestion
- Durable Job Management
- Benchmark Validation
- Benchmark Manifest
- ADE Data Contracts
- Permanent Model Store
- Streamlit Parse Workspace
- Handbook Generation
- Organize Workflows
- Output Export Pipeline
- Session Cost Tracking
- Application Launchers
- Streamlit App Tests
- Streamlit Runtime
- Annotated PDF Generation
- Engine Configuration
- Release Automation
- streamlit_runner
- Document
- agnes_document
- benchmark
- anthropic_document
- pdf_inspector_parser
- Namespace
- calibration
- Dependency-Aware Refactoring
- Knowledge Graph Debugging
- Grounded Outputs
- Contribution Guidelines
- init
- Paperplane Architecture
- build_app_guide
- Paperplane Project Contract
- Benchmark Manifest
- cursor/mcp
- Secure Local Boundary
- Run Paperplane
- Paperplane: zero to mastery PDF
- settings/mcp
- mcp
- qoder/mcp
- Dependency Update Automation
- Better Harness Task-Loop Report
- Direct Bounded Page Processing
- Paperplane 5.2.0 System Architecture
- Paperplane Deployment
- Explicit Exclusive Engine Selection
- Frequently Asked Questions
- Paperplane Processing Flow
- Migration Guide
- Session Cost Estimates
- Calibrated Confidence
- Local Runbook
- Streamlit Theme Boundary
- Artifact Preview
- Document Engines
- Grounded Outputs
- crg-session-start.sh
- crg-update.sh
- DocETL PublicWaterMassMailing Asset
- Safe Support Reporting
- Paperplane v4 Streamlit-Only Migration
- Graph-First Code Discovery
- Pre-Commit Quality Gates
- Release History
- Community Standards
- User Responsibility Disclaimer
- ADR Review Boundary
- Architecture Decision Records
- JobStore and DurableJobService
- Safe Model Output Rendering
- Session State and Cost Ledger
- Document-First Workspace
- Bounded Latency Design
- Validated Grounded Assembler
- Latency Design Invariants
- Durable Local Jobs
- Bug Report Form
- Private Vulnerability Reporting
- Feature Request Form
- Vision Model Integration Request
- Pull Request Validation
- Benchmark Transparency Report
- Verify Streamlit App Workflow
- Contributor Onboarding
- agentic-document-extraction
- Qoder Project Context
- Source Release Process
- Public Water Mass Mailing Scanned

## God Nodes (most connected - your core abstractions)
1. `BoundingBox` - 82 edges
2. `V2PageProcessor` - 71 edges
3. `OpenAIUsage` - 69 edges
4. `StructuredGeneration` - 60 edges
5. `RenderedPage` - 58 edges
6. `ParseResponse` - 52 edges
7. `NativeWord` - 39 edges
8. `NormalizedBox` - 38 edges
9. `AgenticPageInput` - 38 edges
10. `ProcessingMode` - 38 edges

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
- **Shared Project Contract** — agents_project_contract, claude_project_contract, codebuddy_project_contract [INFERRED 0.95]
- **Paperplane Local Runtime Architecture** — docs_adr_0002_langgraph_for_pipeline_direct_bounded_page_processing, docs_adr_0004_secure_by_default_secure_local_boundary, docs_architecture_paperplane_system_pipeline_components [INFERRED 0.75]
- **Paperplane Local Operation** — docs_setup_setup, docs_run_app_run_paperplane, docs_runbook_local_runbook [INFERRED 0.85]
- **Document Processing Workflow** — docs_app_capabilities_paperplane_capabilities, docs_zero_to_mastery_parse_workflow, docs_app_capabilities_grounded_outputs [INFERRED 0.85]

## Communities (95 total, 52 thin omitted)

### Community 0 - "AI Provider Adapters"
Cohesion: 0.08
Nodes (83): align_text_to_native_words(), map_crop_box_to_page(), _padded_box(), Deterministic rendering and coordinate transforms for V2 grounding., Return the exact union of a contiguous native-word match., render_crop(), RenderedCrop, _token() (+75 more)

### Community 1 - "Document Contracts and Docling"
Cohesion: 0.07
Nodes (63): classes_from_text(), Classify, Split, and Section workflows., EngineKind, ADEBilling, ADEBox, ADEGrounding, ADEParseMetadata, ADEParseResponse (+55 more)

### Community 2 - "Grounding and Geometry"
Cohesion: 0.08
Nodes (48): Exception, OllamaDocumentAdapter, OllamaModel, OllamaRequestError, Any, AsyncClient, RuntimeError, Ollama discovery and structured vision adapter. (+40 more)

### Community 3 - "Runtime Model Integration"
Cohesion: 0.08
Nodes (55): _add_generation_usage(), _best_fallback_content(), _cache_key(), _fallback_content(), _generation_model_usage(), _is_scan_like(), _is_semantic_visual_markdown(), _merge_figure_groups() (+47 more)

### Community 4 - "Ollama OCR Pipeline"
Cohesion: 0.11
Nodes (16): job_store(), Durable job history and artifact controls., Connection, JobStatus, DurableJobService, Job, JobStore, _now() (+8 more)

### Community 5 - "Document Ingestion"
Cohesion: 0.14
Nodes (32): AgenticBlockInput, AgenticPageInput, _assemble_atomic_grounding(), assemble_parse_response(), AtomicGrounding, AtomicLineInput, _find_sequential(), _find_table_cell() (+24 more)

### Community 6 - "Durable Job Management"
Cohesion: 0.11
Nodes (29): GroundedWord, NormalizedBox, A document-relative bounding box with coordinates in the [0, 1] interval., An observed native/OCR word aligned to exact Markdown text., DocumentInputError, extract_native_words(), extract_ocr_words(), _rapid_ocr() (+21 more)

### Community 7 - "Benchmark Validation"
Cohesion: 0.12
Nodes (23): AcceleratorDevice, DocItem, DoclingDocument, DocumentConverter, FigureDescriber, _atomic_lines(), create_docling_converter(), DoclingDocumentParser (+15 more)

### Community 8 - "Benchmark Manifest"
Cohesion: 0.23
Nodes (23): DoclingParseResult, AgenticDocumentParser, Process every page immediately and return one grounded response., PdfInspectorParseResult, GroundedChunk, PageResult, BaseModel, FakeDocling (+15 more)

### Community 9 - "ADE Data Contracts"
Cohesion: 0.07
Nodes (28): documents, engines, metrics, version, agnes-2.5-flash, AuditAid/PaddleOCR-VL-1.6-0.9B:latest, calibration_brier, calibration_ece (+20 more)

### Community 10 - "Permanent Model Store"
Cohesion: 0.17
Nodes (17): default_model_root(), _download_docling(), _download_layout(), _legacy_docling_models(), _legacy_layout_snapshot(), main(), ModelStore, ModelStoreStatus (+9 more)

### Community 11 - "Streamlit Parse Workspace"
Cohesion: 0.11
Nodes (22): cache_data, DocumentModel, _build_artifacts(), _cached_pdf_subset(), _capture_uploads(), _clear_workspace(), _count_blocks(), _format_cost_usd() (+14 more)

### Community 12 - "Handbook Generation"
Cohesion: 0.14
Nodes (17): BaseDocTemplate, ParagraphStyle, build(), main(), build_pdf(), _code_block(), HandbookTemplate, _inline() (+9 more)

### Community 13 - "Organize Workflows"
Cohesion: 0.18
Nodes (22): inspect_document(), InspectedDocument, _office_mime_type(), Return PDF bytes containing only an inclusive one-based page range., render_page(), subset_pdf_pages(), _image_bytes(), _pdf_bytes() (+14 more)

### Community 14 - "Output Export Pipeline"
Cohesion: 0.17
Nodes (20): build_output_archive(), OutputArchiveEntry, _paper_html_body(), paper_html_fragment(), Safe, portable output files for completed Parse batches., One source document and its generated, downloadable outputs., Convert untrusted layout-aware Markdown into a sanitized HTML document., Return sanitized HTML inside a responsive white paper surface. (+12 more)

### Community 15 - "Session Cost Tracking"
Cohesion: 0.16
Nodes (16): GeminiDocumentAdapter, GeminiRequestError, Any, AsyncClient, Google Gemini Generate Content boundary for grounded document extraction., Raised when Gemini cannot return a structured document result., ChainedStructuredAdapter, Run Ollama first, then let a cloud adapter validate/refine its structured draft. (+8 more)

### Community 16 - "Application Launchers"
Cohesion: 0.13
Nodes (12): dialog, fail(), Paperplane.sh script, Process shutdown support for the local Paperplane UI., Exit successfully after pending Streamlit deltas reach the browser., schedule_process_exit(), UV_LINK_MODE, test_schedule_process_exit_uses_successful_daemon_timer() (+4 more)

### Community 17 - "Streamlit App Tests"
Cohesion: 0.18
Nodes (19): get_document_model(), Return one supported model or reject an unrecognized API identifier., BatchParseRequest, get_docling_parser(), parse_document(), parse_documents(), ProcessingStrategy, Parse one document without retaining a client, upload, or result. (+11 more)

### Community 18 - "Streamlit Runtime"
Cohesion: 0.15
Nodes (13): aggregate_session_usage(), estimated_cost(), format_cost(), Decimal, Current-session token usage and estimated provider cost., estimate_model_cost(), ModelCostEstimate, The supported document-model catalog and its credential requirements. (+5 more)

### Community 19 - "Annotated PDF Generation"
Cohesion: 0.22
Nodes (14): capture_audit_calls(), _emit_audit(), OpenAIDocumentAdapter, Any, AsyncClient, OpenAI Responses API boundary for grounded document extraction., Capture sanitized request/response records for the current async context., _responses_url() (+6 more)

### Community 20 - "Engine Configuration"
Cohesion: 0.32
Nodes (16): AppTest, _clear_api_keys(), _pdf(), _png(), _select_engine(), test_app_accepts_legacy_gemini_key_as_fallback(), test_app_allows_local_document_upload_without_api_key(), test_app_allows_private_agnes_visual_parse() (+8 more)

### Community 21 - "Release Automation"
Cohesion: 0.21
Nodes (14): AgnesDocumentAdapter, AsyncClient, Adapt the pipeline's structured-generation contract to Agnes 2.5 Flash., Response, _content_response(), _png(), asyncio, test_agnes_fails_after_two_invalid_structured_responses() (+6 more)

### Community 22 - "streamlit_runner"
Cohesion: 0.23
Nodes (13): configure_event_loop(), isolate_external_cuda_toolkit(), main(), Start Streamlit with Paperplane's platform event-loop policy., Keep Windows from mixing system CUDA DLLs with PyTorch's bundled runtime., Reject incomplete Torch metadata and incompatible bundled CUDA libraries., Avoid noisy Proactor connection-reset callbacks on Windows., validate_torch_runtime() (+5 more)

### Community 23 - "Document"
Cohesion: 0.29
Nodes (13): Document, Page, AnnotatedPdfArtifact, build_annotated_pdf(), _content_nodes(), _new_report_page(), _pdf_text(), _plain_excerpt() (+5 more)

### Community 24 - "agnes_document"
Cohesion: 0.27
Nodes (12): AgnesRequestError, _chat_completions_url(), _geometry_error(), _json_text(), _normalize_agnes_value(), Any, Agnes Chat Completions boundary for grounded document extraction., Normalize Agnes JSON equivalents that the pipeline already accepts. (+4 more)

### Community 25 - "benchmark"
Cohesion: 0.21
Nodes (11): BenchmarkDocument, BenchmarkManifest, character_accuracy(), expected_calibration_error(), BaseModel, Path, Reproducible benchmark manifests and transparent metric helpers., Normalized character accuracy based on Levenshtein edit distance. (+3 more)

### Community 26 - "anthropic_document"
Cohesion: 0.21
Nodes (8): AnthropicDocumentAdapter, AnthropicRequestError, Any, AsyncClient, Anthropic Messages API boundary for grounded document extraction., Raised when Claude cannot return a structured document result., asyncio, test_anthropic_uses_messages_vision_and_json_schema()

### Community 27 - "pdf_inspector_parser"
Cohesion: 0.35
Nodes (9): _atomic_lines(), _item_box(), _items_box(), parse_pdf_with_inspector(), Any, Adapter from Firecrawl PDF Inspector into Paperplane page inputs., Extract selected PDF pages without OCR or network access., _pdf() (+1 more)

### Community 28 - "Namespace"
Cohesion: 0.33
Nodes (9): Namespace, add_changelog(), command(), current_version(), main(), next_version(), parse_args(), Path (+1 more)

### Community 29 - "calibration"
Cohesion: 0.43
Nodes (6): CalibrationProfile, confidence_for(), ConfidenceResult, BaseModel, Version- and corpus-pinned confidence calibration., test_arbitrary_model_confidence_is_not_presented_as_calibrated()

### Community 30 - "Dependency-Aware Refactoring"
Cohesion: 0.29
Nodes (7): Dependency-Aware Refactoring, Risk-Aware Code Review, Dependency-Aware Refactoring, Risk-Aware Code Review, Dependency-Aware Refactoring, Risk-Aware Code Review, Graph-First Exploration Policy

### Community 32 - "Knowledge Graph Debugging"
Cohesion: 0.33
Nodes (6): Knowledge Graph Debugging, Graph-Powered Codebase Exploration, Knowledge Graph Debugging, Graph-Powered Codebase Exploration, Knowledge Graph Debugging, Graph-Powered Codebase Exploration

### Community 33 - "Grounded Outputs"
Cohesion: 0.33
Nodes (6): Grounded Outputs, Paperplane Capabilities, Job Retention, Parse Workflow, Zero to Mastery, Paperplane Study Handbook

### Community 34 - "Contribution Guidelines"
Cohesion: 0.40
Nodes (5): Contribution Guidelines, Local-First Document Intelligence, Paperplane, Localhost-Only Security Boundary, Security Policy

### Community 35 - "init"
Cohesion: 0.40
Nodes (4): __getattr__(), Any, Paperplane's framework-neutral grounded document parser., Keep lightweight contracts and benchmark tools free from OCR import cost.

### Community 36 - "Paperplane Architecture"
Cohesion: 0.50
Nodes (4): Paperplane Architecture, Versioned Permanent Model Store, Grounded Parse Contract, Local Streamlit Workspace

### Community 37 - "build_app_guide"
Cohesion: 0.50
Nodes (3): build(), Build the reader-friendly HTML capability guide from its Markdown source., Render the Markdown source with navigation and accessible page chrome.

### Community 38 - "Paperplane Project Contract"
Cohesion: 0.67
Nodes (3): Paperplane Project Contract, Paperplane Project Contract, Paperplane Project Contract

### Community 39 - "Benchmark Manifest"
Cohesion: 0.67
Nodes (3): Benchmark Manifest, Development Guide, Verification Workflow

### Community 41 - "Secure Local Boundary"
Cohesion: 0.67
Nodes (3): Secure Local Boundary, Selected-Page Isolation, Paperplane v4 Security Review

### Community 42 - "Run Paperplane"
Cohesion: 0.67
Nodes (3): Run Paperplane, Permanent Model Store, Setup

### Community 43 - "Paperplane: zero to mastery PDF"
Cohesion: 0.67
Nodes (3): Paperplane: zero to mastery PDF, Local Streamlit Launcher, Paperplane: zero to mastery

## Knowledge Gaps
- **113 isolated node(s):** `uvx`, `crg-session-start.sh script`, `crg-update.sh script`, `uvx`, `uvx` (+108 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **52 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ParseResponse` connect `Document Contracts and Docling` to `Document Ingestion`, `Durable Job Management`, `Benchmark Manifest`, `Streamlit Parse Workspace`, `Session Cost Tracking`, `Streamlit App Tests`, `Document`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `OpenAIUsage` connect `AI Provider Adapters` to `Grounding and Geometry`, `Runtime Model Integration`, `Benchmark Manifest`, `Session Cost Tracking`, `Annotated PDF Generation`, `Release Automation`, `agnes_document`, `anthropic_document`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `JobStore` connect `Ollama OCR Pipeline` to `Document Contracts and Docling`, `Streamlit Parse Workspace`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 36 inferred relationships involving `BoundingBox` (e.g. with `RenderedCrop` and `DocumentInputError`) actually correct?**
  _`BoundingBox` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `V2PageProcessor` (e.g. with `AgenticDocumentParser` and `RenderedPage`) actually correct?**
  _`V2PageProcessor` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 40 inferred relationships involving `OpenAIUsage` (e.g. with `AgnesDocumentAdapter` and `AgnesRequestError`) actually correct?**
  _`OpenAIUsage` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `StructuredGeneration` (e.g. with `AgnesDocumentAdapter` and `AgnesRequestError`) actually correct?**
  _`StructuredGeneration` has 37 INFERRED edges - model-reasoned connections that need verification._