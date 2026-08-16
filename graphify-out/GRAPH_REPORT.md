# Graph Report - Agentic-Document-Extraction  (2026-08-16)

## Corpus Check
- 181 files · ~95,122 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1205 nodes · 2833 edges · 83 communities (62 shown, 21 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 476 edges (avg confidence: 0.56)
- Token cost: 0 input · 478,937 output

## Community Hubs (Navigation)
- Agnes provider adapter
- Architecture docs & ADRs
- V2 page processing pipeline
- Cloud adapter catalog
- Jobs page & store
- Parse contracts & grounding
- Capturing/correcting test adapters
- Agent-tool skill mirrors
- Streamlit app entrypoint
- Benchmark manifest schema
- Grounded word validation
- Docling parser types
- Docling parse results
- Model store downloads
- Organize determinism
- Native ingest & OCR
- Reconciliation & normalization
- Handbook PDF builder
- Pipeline fallback & caching
- ADE JSON contracts explained
- Ollama OCR crop pipeline
- Output archive & HTML
- Batch runtime orchestration
- Confidence calibration
- ADE v2 contract types
- Organize workflows module
- Linux launcher script
- Chained Ollama+cloud adapter
- OpenAI provider adapter
- Ollama adapter tests
- Streamlit app tests
- Ollama document adapter
- Grounding coordinate transforms
- Session cost tracking
- Pipeline output contracts
- Community & contributing docs
- Parse response validation
- Streamlit runner & CUDA isolation
- PDF Inspector parser
- Better Harness task report
- Benchmark accuracy metrics
- Gemini provider adapter
- Anthropic provider adapter
- Duplicated agent contract files
- ADE contract & engine docs
- Release script
- Launcher & release assets
- Processing mode policies
- Engine selection options
- Changelog feature history
- Organize response schemas
- ADE v5 export tests
- Processing recipe versioning
- Benchmark policy & sample doc
- Provider extension docs
- Calibration module internals
- Package init & lazy imports
- Gemini model catalog
- Ollama bug report template
- Cursor MCP config
- Provider request errors
- Organize class definitions
- Settings MCP config
- Root MCP config
- Parser engine recipe
- Qoder MCP config
- Issue template config
- Classify document duplicate
- Adapter request errors
- code-review-graph session hook
- code-review-graph update hook
- Feature request template
- Provider request template
- Cost ledger
- Parse sidebar
- Normalized box
- Class definition
- Parse response
- Structure node
- SQLite job lifecycle
- Paperplane product
- Repo root

## God Nodes (most connected - your core abstractions)
1. `BoundingBox` - 50 edges
2. `V2PageProcessor` - 45 edges
3. `Paperplane README` - 41 edges
4. `OpenAIUsage` - 39 edges
5. `AgenticPageInput` - 38 edges
6. `ProcessingMode` - 38 edges
7. `RenderedPage` - 34 edges
8. `assemble_parse_response()` - 33 edges
9. `NormalizedBox` - 32 edges
10. `ParseResponse` - 32 edges

## Surprising Connections (you probably didn't know these)
- `Debug Issue Skill (CodeBuddy)` --semantically_similar_to--> `Debug Issue Skill (Claude)`  [INFERRED] [semantically similar]
  .codebuddy/skills/debug-issue/SKILL.md → .claude/skills/debug-issue/SKILL.md
- `Debug Issue Skill (Gemini)` --semantically_similar_to--> `Debug Issue Skill (Claude)`  [INFERRED] [semantically similar]
  .gemini/skills/debug-issue/SKILL.md → .claude/skills/debug-issue/SKILL.md
- `Explore Codebase Skill (CodeBuddy)` --semantically_similar_to--> `Explore Codebase Skill (Claude)`  [INFERRED] [semantically similar]
  .codebuddy/skills/explore-codebase/SKILL.md → .claude/skills/explore-codebase/SKILL.md
- `Explore Codebase Skill (Gemini)` --semantically_similar_to--> `Explore Codebase Skill (Claude)`  [INFERRED] [semantically similar]
  .gemini/skills/explore-codebase/SKILL.md → .claude/skills/explore-codebase/SKILL.md
- `Refactor Safely Skill (CodeBuddy)` --semantically_similar_to--> `Refactor Safely Skill (Claude)`  [INFERRED] [semantically similar]
  .codebuddy/skills/refactor-safely/SKILL.md → .claude/skills/refactor-safely/SKILL.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Token Efficiency Rules Convention** — _claude_skills_debug_issue_skill_workflow, _claude_skills_explore_codebase_skill_workflow, _claude_skills_refactor_safely_skill_workflow, _claude_skills_review_changes_skill_workflow, concept_get_minimal_context_tool [INFERRED 0.85]
- **Code-Review-Graph MCP Tool Family** — concept_query_graph_tool, concept_semantic_search_nodes_tool, concept_detect_changes_tool, concept_get_impact_radius_tool, concept_get_affected_flows_tool, concept_refactor_tool [INFERRED 0.85]
- **GitHub Contribution Intake Templates** — _github_issue_template_bug_report_template, _github_issue_template_feature_request_template, _github_issue_template_provider_request_template, _github_pull_request_template_doc, _github_issue_template_config_template [EXTRACTED 1.00]
- **Duplicate AI agent contract/instruction files** — agents, claude, codebuddy, qoder, kiro_steering_code_review_graph [INFERRED 0.85]
- **Release and versioning flow** — release, changelog, scripts_release, streamlit_app [EXTRACTED 0.90]
- **Open-source governance documentation set** — code_of_conduct, contributing, support, security, disclaimer [INFERRED 0.80]
- **Exclusive Engine Selection Pattern Across Docs** — docs_codebase_deep_dive_enginesoptionsvalidator, docs_engines_enginetoggleexclusivity, docs_migration_guide_v4tov5enginereplacement, docs_adr_0002_langgraph_for_pipeline_directboundedpageprocessing [INFERRED 0.80]
- **No Fabricated Accuracy Claim Stance** — docs_quality_benchmarkpolicy, docs_limitations_landingaidisclaimer, docs_codebase_deep_dive_confidencecalibrationmatch [INFERRED 0.80]
- **Generated Documentation Drift Gate** — docs_codebase_deep_dive_codebasedeepdive, docs_zero_to_mastery_zerotomastery, docs_zero_to_mastery_rich_richhtml [INFERRED 0.75]
- **Organize Workflow Documentation (Classify/Split/Section)** — docs_explanation_why_organize_is_deterministic_doc, docs_how_to_tune_classify_classes_doc, docs_reference_organize_schemas_doc, docs_tutorials_organize_a_document_doc [EXTRACTED 0.90]
- **ADE v2 / Paperplane v5 JSON Contract Documentation** — docs_explanation_why_two_json_contracts_doc, docs_how_to_extract_grounding_and_confidence_doc, docs_reference_ade_json_schema_doc, docs_tutorials_read_the_json_output_doc [EXTRACTED 0.90]
- **Provider Contract and Extension Documentation** — docs_reference_provider_contract_doc, docs_tutorials_add_a_provider_doc, docs_how_to_extend_a_provider_doc [EXTRACTED 0.90]

## Communities (83 total, 21 thin omitted)

### Community 0 - "Agnes provider adapter"
Cohesion: 0.09
Nodes (39): Document, Page, AgnesDocumentAdapter, AgnesRequestError, _chat_completions_url(), _geometry_error(), _json_text(), _normalize_agnes_value() (+31 more)

### Community 1 - "Architecture docs & ADRs"
Cohesion: 0.06
Nodes (42): ADR 0001: Record Architecture Decisions, ADR 0002: Direct Bounded Page Processing, ADR 0004: Secure Local Boundary, Architecture Overview, Paperplane System Diagram, Codebase Deep Dive, Confidence Calibration Requires Exact (engine, model, version, corpus) Match, EngineOptions Pydantic Exclusivity Validator (+34 more)

### Community 2 - "V2 page processing pipeline"
Cohesion: 0.21
Nodes (37): RenderedPage, ProcessingMode, VerificationStatus, V2PageProcessor, StrEnum, _CapturingDisagreeingAdapter, _DisagreeingAdapter, _HugeDraftBoxAdapter (+29 more)

### Community 3 - "Cloud adapter catalog"
Cohesion: 0.05
Nodes (38): DOCUMENT_MODELS, DocumentModel, _emit_audit, generate_structured, OpenAIUsage, Provider literal, StructuredAdapter protocol, StructuredGeneration (+30 more)

### Community 4 - "Jobs page & store"
Cohesion: 0.11
Nodes (14): job_store(), Durable job history and artifact controls., Connection, JobStatus, DurableJobService, Job, JobStore, _now() (+6 more)

### Community 5 - "Parse contracts & grounding"
Cohesion: 0.14
Nodes (31): AgenticBlockInput, AgenticPageInput, _assemble_atomic_grounding(), assemble_parse_response(), AtomicGrounding, AtomicLineInput, CodepointRange, _find_sequential() (+23 more)

### Community 6 - "Capturing/correcting test adapters"
Cohesion: 0.08
Nodes (12): _CapturingAdapter, _CorrectingAdapter, _EmptyDraftRecoveredByVerificationAdapter, _EmptyFigureAdapter, _ExactTextAdapter, _ExactTextWithInvalidDraftBoxAdapter, _generation(), _GroupedFigureAdapter (+4 more)

### Community 7 - "Agent-tool skill mirrors"
Cohesion: 0.11
Nodes (30): Debug Issue Skill (Claude), Explore Codebase Skill (Claude), Refactor Safely Skill (Claude), Review Changes Skill (Claude), Debug Issue Skill (CodeBuddy), Explore Codebase Skill (CodeBuddy), Refactor Safely Skill (CodeBuddy), Review Changes Skill (CodeBuddy) (+22 more)

### Community 8 - "Streamlit app entrypoint"
Cohesion: 0.10
Nodes (25): cache_data, _build_artifacts(), _cached_ollama_models(), _cached_pdf_subset(), _capture_uploads(), _clear_workspace(), _count_blocks(), _discover_ollama() (+17 more)

### Community 9 - "Benchmark manifest schema"
Cohesion: 0.07
Nodes (28): documents, engines, metrics, version, agnes-2.5-flash, AuditAid/PaddleOCR-VL-1.6-0.9B:latest, calibration_brier, calibration_ece (+20 more)

### Community 10 - "Grounded word validation"
Cohesion: 0.12
Nodes (24): GroundedWord, An observed native/OCR word aligned to exact Markdown text., DocumentInputError, extract_native_words(), Validate an inclusive one-based range and return its page numbers., Extract observed native PDF words without rendering the page., select_page_range(), convert_office_to_pdf() (+16 more)

### Community 11 - "Docling parser types"
Cohesion: 0.14
Nodes (21): AcceleratorDevice, DocItem, DoclingDocument, DocumentConverter, FigureDescriber, _atomic_lines(), create_docling_converter(), DoclingDocumentParser (+13 more)

### Community 12 - "Docling parse results"
Cohesion: 0.20
Nodes (21): DoclingParseResult, AgenticDocumentParser, Process every page immediately and return one grounded response., PageResult, BaseModel, FakeDocling, FakeFigureDocling, FakeProcessor (+13 more)

### Community 13 - "Model store downloads"
Cohesion: 0.16
Nodes (17): default_model_root(), _download_docling(), _download_layout(), _legacy_docling_models(), _legacy_layout_snapshot(), main(), ModelStore, ModelStoreStatus (+9 more)

### Community 14 - "Organize determinism"
Cohesion: 0.09
Nodes (27): _class_for_text, classify_document, Why Organize is Deterministic, paperplane/document_intelligence.py, Organize Determinism Design, section_document, split_document, ADEParseResponse (+19 more)

### Community 15 - "Native ingest & OCR"
Cohesion: 0.16
Nodes (25): extract_ocr_words(), inspect_document(), InspectedDocument, _office_mime_type(), _rapid_ocr(), Document validation, inspection, rendering, and native word extraction., Return PDF bytes containing only an inclusive one-based page range., Run local OCR and return only word boxes produced by the OCR engine. (+17 more)

### Community 16 - "Reconciliation & normalization"
Cohesion: 0.21
Nodes (25): assess_page_quality(), clean_repeated_labels(), extract_critical_tokens(), normalize_extracted_text(), normalized_key(), PageQualityAssessment, Deterministic quality gates and reconciliation helpers for V2 page drafts., requires_precision_verification() (+17 more)

### Community 17 - "Handbook PDF builder"
Cohesion: 0.14
Nodes (17): BaseDocTemplate, ParagraphStyle, build(), main(), build_pdf(), _code_block(), HandbookTemplate, _inline() (+9 more)

### Community 18 - "Pipeline fallback & caching"
Cohesion: 0.19
Nodes (23): _best_fallback_content(), _cache_key(), _fallback_content(), _is_scan_like(), _is_semantic_visual_markdown(), _merge_figure_groups(), _merge_reconciled_chunks(), _needs_figure_reconciliation() (+15 more)

### Community 19 - "ADE JSON contracts explained"
Cohesion: 0.09
Nodes (23): Why Two JSON Contracts, LandingAI ADE, docs/QUALITY.md, README.md Outputs and contracts section, How to Extract Grounding and Confidence, ADEGrounding, ADEParseMetadata, ADEParseResponse (+15 more)

### Community 20 - "Ollama OCR crop pipeline"
Cohesion: 0.14
Nodes (16): AsyncClient, crop_region(), deduplicate_regions(), ensure_layout_model(), get_layout_detector(), LayoutDetector, LayoutRegion, main() (+8 more)

### Community 21 - "Output archive & HTML"
Cohesion: 0.17
Nodes (20): build_output_archive(), OutputArchiveEntry, _paper_html_body(), paper_html_fragment(), Safe, portable output files for completed Parse batches., One source document and its generated, downloadable outputs., Convert untrusted layout-aware Markdown into a sanitized HTML document., Return sanitized HTML inside a responsive white paper surface. (+12 more)

### Community 22 - "Batch runtime orchestration"
Cohesion: 0.19
Nodes (20): BatchParseOutcome, BatchParseRequest, BatchProgressEvent, get_docling_parser(), parse_document(), parse_documents(), ProcessingStrategy, Short-lived runtime composition for local, bounded batch parsing. (+12 more)

### Community 23 - "Confidence calibration"
Cohesion: 0.16
Nodes (17): Paperplane contributor onboarding, CalibrationProfile, confidence_for(), ConfidenceResult, BaseModel, Version- and corpus-pinned confidence calibration., Document hierarchy node, ordered as document → page → block → table cell., StructureNode (+9 more)

### Community 24 - "ADE v2 contract types"
Cohesion: 0.21
Nodes (20): ADEBilling, ADEBox, ADEGrounding, ADEParseMetadata, ADEParseResponse, ADERange, ADEStructureNode, _box() (+12 more)

### Community 25 - "Organize workflows module"
Cohesion: 0.24
Nodes (17): classes_from_text(), Classify, Split, and Section workflows., _class_for_text(), ClassDefinition, ClassifiedPage, classify_document(), ClassifyResponse, _page_ranges() (+9 more)

### Community 26 - "Linux launcher script"
Cohesion: 0.13
Nodes (12): dialog, fail(), Paperplane.sh script, Process shutdown support for the local Paperplane UI., Exit successfully after pending Streamlit deltas reach the browser., schedule_process_exit(), UV_LINK_MODE, test_schedule_process_exit_uses_successful_daemon_timer() (+4 more)

### Community 27 - "Chained Ollama+cloud adapter"
Cohesion: 0.17
Nodes (12): ChainedStructuredAdapter, Any, Run Ollama first, then let a cloud adapter validate/refine its structured draft., OpenAIUsage, BaseModel, StructuredGeneration, _add_generation_usage(), _generation_model_usage() (+4 more)

### Community 28 - "OpenAI provider adapter"
Cohesion: 0.20
Nodes (16): capture_audit_calls(), _emit_audit(), OpenAIDocumentAdapter, OpenAIRequestError, Any, AsyncClient, RuntimeError, OpenAI Responses API boundary for grounded document extraction. (+8 more)

### Community 29 - "Ollama adapter tests"
Cohesion: 0.30
Nodes (18): OllamaDocumentAdapter, clean_ocr_output(), FakeThreeRegionDetector, _png(), asyncio, test_chained_adapter_preserves_local_and_cloud_warnings(), test_deepseek_aborts_after_three_consecutive_exhausted_regions(), test_deepseek_does_not_retry_nontransient_http_error() (+10 more)

### Community 30 - "Streamlit app tests"
Cohesion: 0.30
Nodes (17): AppTest, _clear_api_keys(), _pdf(), _png(), _select_engine(), test_app_accepts_legacy_gemini_key_as_fallback(), test_app_allows_local_document_upload_without_api_key(), test_app_allows_private_agnes_visual_parse() (+9 more)

### Community 31 - "Ollama document adapter"
Cohesion: 0.16
Nodes (11): Exception, OllamaModel, OllamaRequestError, RuntimeError, Ollama discovery and structured vision adapter., _retryable_ocr_error(), chunk_type_for_label(), OcrProfile (+3 more)

### Community 32 - "Grounding coordinate transforms"
Cohesion: 0.21
Nodes (15): align_text_to_native_words(), map_crop_box_to_page(), _padded_box(), Deterministic rendering and coordinate transforms for V2 grounding., Return the exact union of a contiguous native-word match., render_crop(), RenderedCrop, _token() (+7 more)

### Community 33 - "Session cost tracking"
Cohesion: 0.15
Nodes (12): aggregate_session_usage(), estimated_cost(), format_cost(), Decimal, Current-session token usage and estimated provider cost., estimate_model_cost(), ModelCostEstimate, Estimate one parse at the configured per-million-token rates. (+4 more)

### Community 34 - "Pipeline output contracts"
Cohesion: 0.23
Nodes (12): AtomicLine, GroundedChunk, Grounding, GroundingMethod, mode_policy(), ModePolicy, BaseModel, Grounded contracts used by the OpenAI page pipeline. (+4 more)

### Community 35 - "Community & contributing docs"
Cohesion: 0.18
Nodes (15): Code of Conduct, Contributing guide, PP-DocLayoutV3 pinned to CPU to preserve GPU VRAM for Ollama models, Disclaimer and User Responsibility, docs/ARCHITECTURE.md, docs/DEVELOPMENT.md, No auto-routing: exactly one explicit engine per run, No donations/sponsorships policy (+7 more)

### Community 36 - "Parse response validation"
Cohesion: 0.22
Nodes (5): ParseResponse, model_validator, model_validator, model_validator, ValueError

### Community 37 - "Streamlit runner & CUDA isolation"
Cohesion: 0.23
Nodes (13): configure_event_loop(), isolate_external_cuda_toolkit(), main(), Start Streamlit with Paperplane's platform event-loop policy., Keep Windows from mixing system CUDA DLLs with PyTorch's bundled runtime., Reject incomplete Torch metadata and incompatible bundled CUDA libraries., Avoid noisy Proactor connection-reset callbacks on Windows., validate_torch_runtime() (+5 more)

### Community 38 - "PDF Inspector parser"
Cohesion: 0.27
Nodes (12): NormalizedBox, A document-relative bounding box with coordinates in the [0, 1] interval., _atomic_lines(), _item_box(), _items_box(), parse_pdf_with_inspector(), PdfInspectorParseResult, Any (+4 more)

### Community 39 - "Better Harness task report"
Cohesion: 0.17
Nodes (13): Better Harness Task-Loop Report (HTML), Better Harness Task-Loop Report (Markdown), Failed document parses cannot be correlated with promised logs, Reviewed window cannot classify recurring implementation friction, Recent task handoffs do not retain final-change verification, Hybrid parser fallback can change without a focused regression failure, Managed environment blocks focused parser checks, Dependabot Configuration (+5 more)

### Community 40 - "Benchmark accuracy metrics"
Cohesion: 0.22
Nodes (11): BenchmarkDocument, BenchmarkManifest, character_accuracy(), expected_calibration_error(), BaseModel, Path, Reproducible benchmark manifests and transparent metric helpers., Normalized character accuracy based on Levenshtein edit distance. (+3 more)

### Community 41 - "Gemini provider adapter"
Cohesion: 0.19
Nodes (9): GeminiDocumentAdapter, GeminiRequestError, Any, AsyncClient, Google Gemini Generate Content boundary for grounded document extraction., Raised when Gemini cannot return a structured document result., asyncio, parametrize (+1 more)

### Community 42 - "Anthropic provider adapter"
Cohesion: 0.21
Nodes (8): AnthropicDocumentAdapter, AnthropicRequestError, Any, AsyncClient, Anthropic Messages API boundary for grounded document extraction., Raised when Claude cannot return a structured document result., asyncio, test_anthropic_uses_messages_vision_and_json_schema()

### Community 43 - "Duplicated agent contract files"
Cohesion: 0.38
Nodes (10): AGENTS.md project contract, CLAUDE.md project contract, CODEBUDDY.md project contract, docs/MODELS.md, Kiro steering: code-review-graph MCP tools, code-review-graph MCP tool usage rule, DocumentModel, get_document_model() (+2 more)

### Community 44 - "ADE contract & engine docs"
Cohesion: 0.31
Nodes (11): ADE v2-style Parse JSON contract, Paperplane v5 JSON contract, Windows CUDA/cuDNN runtime isolation from system DLLs, App Capabilities (Markdown), Cloud AI ADE engine, Docling ADE engine, Ollama ADE engine, PDF Inspector ADE engine (+3 more)

### Community 45 - "Release script"
Cohesion: 0.33
Nodes (9): Namespace, add_changelog(), command(), current_version(), main(), next_version(), parse_args(), Path (+1 more)

### Community 46 - "Launcher & release assets"
Cohesion: 0.22
Nodes (8): App Capabilities (HTML), Paperplane.cmd (Windows launcher), pre-commit hook configuration, Source release process, build(), Build the reader-friendly HTML capability guide from its Markdown source., Render the Markdown source with navigation and accessible page chrome., Semantic Versioning for source-only GitHub releases

### Community 47 - "Processing mode policies"
Cohesion: 0.22
Nodes (9): _MODE_POLICIES, ModePolicy, ProcessingMode, AgenticDocumentParser, Archived Plan: Balanced PDF Latency, Fast/Balanced/Audit modes, Balanced mode drafting/reconciliation/verification design, Archived Design: Balanced PDF Latency (+1 more)

### Community 48 - "Engine selection options"
Cohesion: 0.28
Nodes (4): EngineKind, EngineOptions, model_validator, UI-neutral engine switches. An empty selection is valid until Parse is pressed.

### Community 49 - "Changelog feature history"
Cohesion: 0.25
Nodes (7): Cost workspace page (per-model token accounting), Evidence-grounded extraction (v0.5.0), dependency-review.yml CI workflow, JobQueue protocol (InProcess/Arq backends) v0.3.0, MCP server (stdio) support added v0.6.0, v0.3.0 modernization release, Semantic-versioning source release process

### Community 50 - "Organize response schemas"
Cohesion: 0.25
Nodes (8): ClassifiedPage, ClassifyResponse, CodepointRange, SectionResponse, SectionResult, sections.json (downloaded file), SplitResponse, SplitResult

### Community 51 - "ADE v5 export tests"
Cohesion: 0.36
Nodes (7): _box(), Path, _response(), test_engine_options_are_exclusive_and_cloud_cannot_enhance(), test_job_store_persists_checkpoints_and_purges_expired_artifacts(), test_paperplane_export_includes_per_model_usage_without_changing_ade(), test_strict_ade_v2_parse_export_has_inline_grounding_and_zero_based_ids()

### Community 52 - "Processing recipe versioning"
Cohesion: 0.38
Nodes (6): processing_recipe(), ProcessingRecipe, BaseModel, RecipeVersion, Versioned processing recipes with an operator rollback path., VerificationBudget

### Community 54 - "Benchmark policy & sample doc"
Cohesion: 0.33
Nodes (6): Locked benchmark evaluation policy, Benchmarks directory README, DocETL upstream project (sample PDF source), LandingAI ADE (external inspiration, not a dependency), PublicWaterMassMailing.pdf sample document, Sample document attribution README

### Community 55 - "Provider extension docs"
Cohesion: 0.40
Nodes (6): How to Extend an Existing Provider, why-explicit-providers.md, Provider Contract Reference, why-explicit-providers.md, Tutorial: Add a New Cloud AI Provider, why-explicit-providers.md

### Community 56 - "Calibration module internals"
Cohesion: 0.33
Nodes (6): paperplane/calibration.py, CalibrationProfile, calibration.confidence_for, paperplane/contracts.py, GroundedWord, ParseResponse

### Community 57 - "Package init & lazy imports"
Cohesion: 0.40
Nodes (4): __getattr__(), Any, Paperplane's framework-neutral grounded document parser., Keep lightweight contracts and benchmark tools free from OCR import cost.

### Community 58 - "Gemini model catalog"
Cohesion: 0.50
Nodes (4): paperplane/gemini_document.py, GEMINI_MODELS, generate_structured, paperplane/pipeline.py

### Community 59 - "Ollama bug report template"
Cohesion: 0.67
Nodes (3): Bug Report Issue Template, glm-ocr:latest model, Ollama ADE (processing engine)

### Community 61 - "Provider request errors"
Cohesion: 0.67
Nodes (3): GeminiRequestError, OpenAIRequestError, paperplane/runtime.py

### Community 62 - "Organize class definitions"
Cohesion: 0.67
Nodes (3): ClassDefinition, classes_from_text, app_pages/organize.py

## Ambiguous Edges - Review These
- `Better Harness Task-Loop Report (Markdown)` → `Better Harness Task-Loop Report (HTML)`  [AMBIGUOUS]
  .codex/better-harness/20260814-181137Z/report.html · relation: semantically_similar_to
- `Seven-day local SQLite job/artifact history` → `No application persistence or cross-session result cache`  [AMBIGUOUS]
  security_best_practices_report.md · relation: conceptually_related_to

## Knowledge Gaps
- **157 isolated node(s):** `uvx`, `crg-session-start.sh script`, `crg-update.sh script`, `uvx`, `uvx` (+152 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Better Harness Task-Loop Report (Markdown)` and `Better Harness Task-Loop Report (HTML)`?**
  _Edge tagged AMBIGUOUS (relation: semantically_similar_to) - confidence is low._
- **What is the exact relationship between `Seven-day local SQLite job/artifact history` and `No application persistence or cross-session result cache`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Paperplane README` connect `Community & contributing docs` to `Jobs page & store`, `Streamlit app entrypoint`, `Benchmark manifest schema`, `Grounded word validation`, `Docling parser types`, `Model store downloads`, `Output archive & HTML`, `Batch runtime orchestration`, `Confidence calibration`, `ADE v2 contract types`, `Organize workflows module`, `Linux launcher script`, `Ollama document adapter`, `PDF Inspector parser`, `Benchmark accuracy metrics`, `Duplicated agent contract files`, `ADE contract & engine docs`, `Launcher & release assets`, `Changelog feature history`, `Benchmark policy & sample doc`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Why does `Paperplane contributor onboarding` connect `Confidence calibration` to `Community & contributing docs`, `Jobs page & store`, `Benchmark accuracy metrics`, `Streamlit app entrypoint`, `Grounded word validation`, `Model store downloads`, `Launcher & release assets`, `Handbook PDF builder`, `Output archive & HTML`, `Batch runtime orchestration`, `ADE v2 contract types`, `Organize workflows module`, `Linux launcher script`, `Ollama document adapter`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `OpenAIUsage` connect `Chained Ollama+cloud adapter` to `Agnes provider adapter`, `V2 page processing pipeline`, `Pipeline output contracts`, `Capturing/correcting test adapters`, `Gemini provider adapter`, `Anthropic provider adapter`, `Docling parse results`, `Pipeline fallback & caching`, `OpenAI provider adapter`, `Ollama adapter tests`, `Ollama document adapter`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Are the 37 inferred relationships involving `BoundingBox` (e.g. with `align_text_to_native_words()` and `map_crop_box_to_page()`) actually correct?**
  _`BoundingBox` has 37 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `V2PageProcessor` (e.g. with `AgenticDocumentParser` and `RenderedPage`) actually correct?**
  _`V2PageProcessor` has 34 INFERRED edges - model-reasoned connections that need verification._