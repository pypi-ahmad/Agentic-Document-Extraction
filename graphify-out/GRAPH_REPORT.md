# Graph Report - .  (2026-08-14)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1832 nodes · 3652 edges · 140 communities (122 shown, 18 thin omitted)
- Extraction: 75% EXTRACTED · 25% INFERRED · 0% AMBIGUOUS · INFERRED: 908 edges (avg confidence: 0.67)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2dabe190`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- V2PageProcessor
- schema_extraction.py
- QualityScore
- contracts.py
- VisionProviderRegistry
- evaluate_document
- extraction.py
- GroundedChunk
- devDependencies
- PageResult
- Region
- QualityOverrides
- client
- v2_accuracy.py
- constants.py
- supervisor.py
- compilerOptions
- GlmOcrLayoutEngine
- LayoutParser
- .process_page
- artifacts.py
- handbook_pdf.py
- rate_limit.py
- release.py
- ParseSettings
- DocumentInputError
- page.tsx
- test_rate_limit.py
- markdown.py
- _NoopSpan
- logging_setup.py
- main.py
- LayoutEngine
- Results
- BoundingBox
- Added
- AgenticSchemaExtractor
- VisionZoneEngine
- build_subdocument_payloads
- validated_base_url
- dpt_api.py
- runtime_capabilities
- openai_document.py
- dev.ps1
- enums.py
- _run_launcher
- manifest.json
- code-review-graph
- next.config.js
- layout.tsx
- code-review-graph
- code-review-graph
- code-review-graph
- __init__.py
- __init__.py
- AgenticDocumentParser
- next-env.d.ts
- crg-session-start.sh
- crg-update.sh
- agentic-document-extraction
- run_matrix
- Changelog
- Task List
- CHANGELOG.md
- ARCHITECTURE.md
- Balanced PDF Latency Design
- Fix Agentic V2 Pipeline Review Findings
- network.py
- Run Paperplane
- Global Constraints
- Evidence Studio Design
- Welcome to [Team Name]
- telemetry.py
- CONTRIBUTING.md
- Contributing
- FAQ
- README.md
- Paperplane threat model
- OllamaReviewer
- Code of Conduct
- File Structure
- Global Constraints
- Dark Theme Design
- Paperplane from zero to mastery
- Release process
- 3. Cutting a release
- require_rate_limit
- FakeParser
- [1.0.0] - 2026-07-23
- ADR 0001 — Record architecture decisions
- Paperplane capabilities
- MCP Tools: code-review-graph
- MCP Tools: code-review-graph
- Debug Issue
- Explore Codebase
- Refactor Safely
- Review Changes
- MCP Tools: code-review-graph
- Debug Issue
- Explore Codebase
- Refactor Safely
- Review Changes
- Operations runbook
- V2 Output Quality Implementation Plan
- MCP Tools: code-review-graph
- Debug Issue
- Explore Codebase
- Refactor Safely
- Review Changes
- MCP Tools: code-review-graph
- MCP Tools: code-review-graph
- MCP Tools: code-review-graph
- Security best-practices review
- [2.0.0] - 2026-07-26
- [Unreleased]
- ADR 0002 — Bounded page processing
- ADR 0004 — Secure-by-default HTTP boundary
- ENGINES.md
- MCP.md
- observability.md
- QUALITY.md
- SETUP.md

## God Nodes (most connected - your core abstractions)
1. `BoundingBox` - 77 edges
2. `V2PageProcessor` - 56 edges
3. `Region` - 55 edges
4. `RenderedPage` - 53 edges
5. `DocumentLayout` - 40 edges
6. `LayoutParser` - 36 edges
7. `OpenAIUsage` - 35 edges
8. `VisionProviderRegistry` - 31 edges
9. `ParseSettings` - 30 edges
10. `PageLayout` - 29 edges

## Surprising Connections (you probably didn't know these)
- `test_canary_accepts_loopback_targets()` --calls--> `validated_base_url()`  [EXTRACTED]
  backend/tests/unit/test_live_canary.py → scripts/live_canary.py
- `test_canary_rejects_remote_target_without_explicit_consent()` --calls--> `validated_base_url()`  [EXTRACTED]
  backend/tests/unit/test_live_canary.py → scripts/live_canary.py
- `test_canary_rejects_plaintext_remote_target_even_with_consent()` --calls--> `validated_base_url()`  [EXTRACTED]
  backend/tests/unit/test_live_canary.py → scripts/live_canary.py
- `test_canary_accepts_explicit_https_remote_target()` --calls--> `validated_base_url()`  [EXTRACTED]
  backend/tests/unit/test_live_canary.py → scripts/live_canary.py
- `test_agentic_settings_reject_out_of_range_values()` --calls--> `Settings`  [INFERRED]
  backend/tests/unit/test_parse_config.py → backend/app/config.py

## Import Cycles
- None detected.

## Communities (140 total, 18 thin omitted)

### Community 0 - "V2PageProcessor"
Cohesion: 0.09
Nodes (60): NativeWord, RenderedPage, OpenAIUsage, BaseModel, StructuredGeneration, GroundingMethod, ProcessingMode, StrEnum (+52 more)

### Community 1 - "schema_extraction.py"
Cohesion: 0.08
Nodes (72): _block_citation(), _cell_citation(), _coerce(), _evidence_index(), _extract_object_fields(), extract_schema_instance(), ExtractionScope, ExtractionValidationError (+64 more)

### Community 2 - "QualityScore"
Cohesion: 0.08
Nodes (59): AttemptRecord, DocumentContext, ExpertKind, PageDiagnostics, PageObservation, PagePlan, PlanningMode, ProcessingStage (+51 more)

### Community 3 - "contracts.py"
Cohesion: 0.12
Nodes (24): AgenticBlockInput, AgenticPageInput, _assemble_atomic_grounding(), assemble_parse_response(), AtomicGrounding, AtomicLineInput, CodepointRange, ExtractionResponse (+16 more)

### Community 4 - "VisionProviderRegistry"
Cohesion: 0.06
Nodes (51): Configuration for the local document-to-Markdown service., Settings, ProviderReviewer, BaseModel, RuntimeError, Structured visual alignment review through a local Ollama VLM., Compare a page and Markdown through a configured cloud vision provider., Raised when the local reviewer cannot return a valid result. (+43 more)

### Community 5 - "evaluate_document"
Cohesion: 0.08
Nodes (52): _align(), evaluate_document(), EvaluationReport, _gold_cell_objects(), _gold_cell_text(), GoldPage, GoldRegion, GoldSubDocument (+44 more)

### Community 6 - "extraction.py"
Cohesion: 0.16
Nodes (24): _build_metadata(), ExtractionRequest, ExtractionResult, ExtractionServiceError, _fallback_evidence(), _format_schema_violations(), InvalidExtractionSchemaError, InvalidGroundingEvidenceError (+16 more)

### Community 7 - "GroundedChunk"
Cohesion: 0.05
Nodes (66): build_annotated_pdf(), Document, Generate downloadable PDFs with auditable V2 region overlays., _source_pdf(), DocumentItem, DocumentPage, DocumentResult, DocumentSplit (+58 more)

### Community 8 - "devDependencies"
Cohesion: 0.05
Nodes (43): autoprefixer, eslint, eslint-config-next, dependencies, lucide-react, next, react, react-dom (+35 more)

### Community 9 - "PageResult"
Cohesion: 0.08
Nodes (23): FileStore, ObjectStore, Path, Protocol, Path-safe storage for sources, checkpoints, and generated artifacts., blob_path(), build_bundle(), canonical_json() (+15 more)

### Community 10 - "Region"
Cohesion: 0.19
Nodes (25): DocumentLayout, PageLayout, BaseModel, Normalized parser contracts independent of any specific OCR engine's SDK payload, Region, StitchResult, TableCell, MarkdownRenderer (+17 more)

### Community 11 - "QualityOverrides"
Cohesion: 0.11
Nodes (36): ArtifactResponse, ExtractionSchemaListResponse, ExtractionSchemaResponse, ExtractionSchemaSnapshotSummary, ExtractionSchemaValidateRequest, ExtractionSchemaValidationError, ExtractionSchemaValidationResponse, ExtractionSchemaWrite (+28 more)

### Community 12 - "client"
Cohesion: 0.18
Nodes (12): OllamaCatalogUnavailable, OllamaModel, OllamaModelCatalog, AsyncClient, BaseModel, RuntimeError, Discovery and capability validation for models installed in Ollama., client() (+4 more)

### Community 13 - "v2_accuracy.py"
Cohesion: 0.15
Nodes (16): classify_markdown_types(), compare_markdown_accuracy(), _edit_distance(), _metrics(), _plain(), Deterministic Markdown accuracy metrics used by live extraction benchmarks., Split reference Markdown into stable, benchmark-oriented content classes., _tokens() (+8 more)

### Community 14 - "constants.py"
Cohesion: 0.18
Nodes (7): ASGIApp, Project-wide constants.  This module is the single source of truth for any str, Request, Security middleware: default security headers on every response.  These are th, Attach the standard security headers to every response., SecurityHeadersMiddleware, BaseHTTPMiddleware

### Community 15 - "supervisor.py"
Cohesion: 0.10
Nodes (23): AdaptiveDocumentSupervisor, Critic, DocumentGraphState, ModelProfile, _normalise_roles(), PageAssessor, Any, Protocol (+15 more)

### Community 16 - "compilerOptions"
Cohesion: 0.06
Nodes (30): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+22 more)

### Community 17 - "GlmOcrLayoutEngine"
Cohesion: 0.13
Nodes (19): GlmOcrLayoutEngine, GlmOcrResponseError, GlmOcrUnavailable, AsyncClient, HTMLParser, Path, RuntimeError, Layout + first-pass OCR via a self-hosted GLM-OCR pipeline server.  Talks to t (+11 more)

### Community 18 - "LayoutParser"
Cohesion: 0.14
Nodes (20): build_parser_graph(), ParserState, Any, TypedDict, Document-wide LangGraph for layout-aware Markdown parsing., reflection_router(), _regions(), LayoutParser (+12 more)

### Community 19 - ".process_page"
Cohesion: 0.08
Nodes (53): Grounding, _best_fallback_content(), _cache_key(), _fallback_content(), _is_scan_like(), _is_semantic_visual_markdown(), _merge_figure_groups(), _merge_reconciled_chunks() (+45 more)

### Community 20 - "artifacts.py"
Cohesion: 0.18
Nodes (15): build_grounding_pdf(), build_searchable_pdf(), build_verification_overlay(), Document, Generate grounded PDFs, searchable PDFs, region crops, and bundles., Draw exact region coordinates and IDs on a page image for visual verification., _rect(), _selected_pdf() (+7 more)

### Community 21 - "handbook_pdf.py"
Cohesion: 0.15
Nodes (16): BaseDocTemplate, ParagraphStyle, build(), main(), build_pdf(), _code_block(), HandbookTemplate, _inline() (+8 more)

### Community 22 - "rate_limit.py"
Cohesion: 0.15
Nodes (13): Optional shared-secret auth for exposing the API beyond localhost.  Disabled b, Validate the shared API key. Returns the validated key, or ``None``     when au, require_api_key(), Fixed-window, per-identity request throttling.  Identity is derived from the a, list_ollama_models(), OllamaModelsResponse, BaseModel, Request (+5 more)

### Community 23 - "release.py"
Cohesion: 0.18
Nodes (21): assert_clean_working_tree(), bump(), commits_since(), current_branch(), derive_notes(), _detect_repo(), git(), last_tag() (+13 more)

### Community 24 - "ParseSettings"
Cohesion: 0.19
Nodes (14): ParseSettings, Any, test_public_contract_uses_document_input_mode_and_context_artifact(), test_cloud_context_requires_a_model_when_enabled(), test_legacy_grounding_pdf_false_is_normalized_to_required_output(), test_legacy_review_selection_enables_adaptive_context(), test_parse_settings_defaults_are_safe(), test_parse_settings_rejects_reversed_page_range() (+6 more)

### Community 25 - "DocumentInputError"
Cohesion: 0.11
Nodes (28): DocumentInputError, inspect_document(), InspectedDocument, ValueError, Document validation, inspection, rendering, and native word extraction., render_page(), align_text_to_native_words(), map_crop_box_to_page() (+20 more)

### Community 26 - "page.tsx"
Cohesion: 0.15
Nodes (15): countBlocks(), HomePage(), MODEL_COPY, ResultView, result, Theme, WorkspaceTab, DocumentCanvas() (+7 more)

### Community 27 - "test_rate_limit.py"
Cohesion: 0.12
Nodes (11): FixedWindowLimiter, Allow at most ``limit`` requests per identity per ``window_seconds``., Rebuild the module-level limiter from current settings (test-only)., reset_rate_limiter_for_tests(), AsyncClient, rate_limited_settings(), Enable auth + rate limiting for the duration of one test, then restore., rl_client() (+3 more)

### Community 28 - "markdown.py"
Cohesion: 0.15
Nodes (13): _code_block(), _formula_body(), MarkdownOutput, _normalize_text(), HTMLParser, Deterministic clean and grounded Markdown assembly., Remove one outer math wrapper and keep remaining dollars literal., Render hierarchy-preserving Markdown with machine-readable source anchors. (+5 more)

### Community 29 - "_NoopSpan"
Cohesion: 0.25
Nodes (7): get_tracer(), manual_span(), _NoopSpan, _NoopTracer, Any, Return an OTel tracer, or a no-op if telemetry is disabled.      The no-op tra, Context manager that opens a manual OTel span, or a no-op if     telemetry is d

### Community 30 - "logging_setup.py"
Cohesion: 0.14
Nodes (17): bind_request_id(), clear_request_id(), configure_logging(), get_logger(), _inject_service_name(), log_event(), Any, Return a structlog logger. ``None`` means the root logger. (+9 more)

### Community 31 - "main.py"
Cohesion: 0.13
Nodes (6): info(), lifespan(), Response, FastAPI application for stateless grounded document extraction., readiness(), Shared test fixtures.

### Community 32 - "LayoutEngine"
Cohesion: 0.21
Nodes (6): LayoutEngine, Any, Path, Protocol, Local vision-first layout parsing primitives used by the LangGraph workflow., ZoneEngine

### Community 33 - "Results"
Cohesion: 0.27
Nodes (13): main(), Live validation of LLM model-listing and auto-routing against real provider acco, Check that OpenAI model list filters to gpt-*/o1/o3/o4 prefixes., Check that Gemini filters to generateContent-capable models., Validate auto-routing picks the expected provider., Check which providers are configured and available., Fetch models from a specific provider and validate., Results (+5 more)

### Community 34 - "BoundingBox"
Cohesion: 0.14
Nodes (14): crop_region(), BoundingBox, RecognitionCandidate, Any, Coordinate-aware local checks used before visual model review., verify_region_coordinates(), test_crop_region_uses_normalized_coordinates(), test_build_page_diagnostics_has_deterministic_fallback_without_review() (+6 more)

### Community 35 - "Added"
Cohesion: 0.05
Nodes (42): [0.2.0] - 2026-06-22, [0.3.0] - 2026-06-22, [2026-06-13], Added, Added, Added, Added, Added (+34 more)

### Community 36 - "AgenticSchemaExtractor"
Cohesion: 0.16
Nodes (18): AgenticSchemaExtractor, ExtractionCandidate, A model candidate violates a schema requested with ``strict=True``., Structured Terra output; evidence is keyed by RFC 6901-style leaf paths., Run one injected Terra extraction call, then deterministically validate and grou, StrictSchemaViolationError, Fails if non-strict extraction drops usable candidate values on validation error, Fails if strict mode returns a schema-invalid extraction instead of a 422-ready (+10 more)

### Community 37 - "VisionZoneEngine"
Cohesion: 0.29
Nodes (7): build_default_parser(), _candidate_similarity(), _crop(), Path, Vision-provider zone repair engine for the local parsing pipeline., Repair a low-confidence region using a cloud vision provider., VisionZoneEngine

### Community 38 - "build_subdocument_payloads"
Cohesion: 0.31
Nodes (7): ArtifactPayload, build_subdocument_payloads(), Create sub-document files from an already parsed parent document., _slice_layout(), _slice_source(), _source_pdf(), test_subdocument_exports_selected_pages_and_preserves_source_page_citations()

### Community 39 - "validated_base_url"
Cohesion: 0.39
Nodes (7): test_canary_accepts_explicit_https_remote_target(), test_canary_accepts_loopback_targets(), test_canary_rejects_plaintext_remote_target_even_with_consent(), test_canary_rejects_remote_target_without_explicit_consent(), main(), Opt-in live parse canary; never runs in the offline test suite., validated_base_url()

### Community 40 - "dpt_api.py"
Cohesion: 0.14
Nodes (19): _error(), extract_document(), _extraction_dependency(), ExtractRequest, get_agentic_extractor(), get_invoice_contract(), parse_document(), Any (+11 more)

### Community 41 - "runtime_capabilities"
Cohesion: 0.33
Nodes (6): BaseModel, Request, runtime_capabilities(), RuntimeCapabilitiesResponse, test_runtime_reports_empty_when_runtime_unavailable(), test_runtime_reports_vision_providers()

### Community 42 - "openai_document.py"
Cohesion: 0.18
Nodes (14): capture_audit_calls(), _emit_audit(), OpenAIDocumentAdapter, OpenAIRequestError, Any, AsyncClient, RuntimeError, OpenAI Responses API boundary for grounded document extraction. (+6 more)

### Community 44 - "enums.py"
Cohesion: 0.47
Nodes (5): ArtifactType, JobStatus, PageStatus, StrEnum, Stable string enums used by document-processing contracts.

### Community 45 - "_run_launcher"
Cohesion: 0.60
Nodes (4): CompletedProcess, _run_launcher(), test_dev_launcher_rejects_an_explicit_backend_port_that_is_in_use(), test_dev_launcher_rejects_missing_openai_api_key()

### Community 46 - "manifest.json"
Cohesion: 0.40
Nodes (4): datasets, license, note, version

### Community 56 - "AgenticDocumentParser"
Cohesion: 0.17
Nodes (12): _parser_dependency(), Request, NormalizedBox, A document-relative bounding box with coordinates in the [0, 1] interval., _agentic_page(), AgenticDocumentParser, _atomic_lines(), _normalised_box() (+4 more)

### Community 71 - "run_matrix"
Cohesion: 0.21
Nodes (15): create_schema(), _err(), _make_pdf(), _make_png(), AsyncClient, Safely extract error string from an extraction response., Create a minimal valid PDF with embedded text using PyMuPDF., Create a tiny valid PNG image (1x1 white pixel). (+7 more)

### Community 72 - "Changelog"
Cohesion: 0.15
Nodes (13): [0.3.0] - 2026-06-22, [0.4.0] - 2026-06-22, [0.5.0] - 2026-06-22, [0.6.0] - 2026-06-22, Added, Added, Added, Changed (+5 more)

### Community 73 - "Task List"
Cohesion: 0.15
Nodes (12): Architecture Decisions, Checkpoint: Complete, Checkpoint: Phase 1, Checkpoint: Phase 2, Implementation Plan: Fix Agentic V2 Pipeline Review Findings, Open Questions, Overview, Phase 1: Unblock the feature (Critical, do first — everything else is unreachable until this lands) (+4 more)

### Community 74 - "CHANGELOG.md"
Cohesion: 0.18
Nodes (7): Deployment, Required configuration, Breaking changes, Client migration, Migration guide: stateless V2, Release notes, Unreleased — stateless simplification

### Community 75 - "ARCHITECTURE.md"
Cohesion: 0.20
Nodes (6): Architecture, Boundaries, Request lifecycle, Paperplane V2 architecture, How Paperplane works, Pipeline and agentic architecture

### Community 76 - "Balanced PDF Latency Design"
Cohesion: 0.20
Nodes (9): Accuracy safeguards, Balanced PDF Latency Design, Concurrency and deadline, Current bottleneck, Design, Goal, Observability, Scope (+1 more)

### Community 77 - "Fix Agentic V2 Pipeline Review Findings"
Cohesion: 0.20
Nodes (9): Fix Agentic V2 Pipeline Review Findings, Task 1: Fix dpt_api.py router prefix so the app is reachable end-to-end, Task 2: Table cells get correct row/col instead of fabricated values, Task 3: Fix draft-chunk matching boosting candidates with unparseable boxes, Task 4: Fix parent_order remap after figure-group merge shifts positions, Task 5: Evaluation raises a clean 4xx on page-count mismatch, Task 6: Frontend document preview uses apiResourceUrl() for source_preview_url, Task 7: Fix duplicate-sibling substring-containment false positive (+1 more)

### Community 78 - "network.py"
Cohesion: 0.28
Nodes (8): _is_loopback_host(), ValueError, Network guard for local-only services (e.g. local Ollama).  By default, ``OLLA, Raised when OLLAMA_BASE_URL points at a non-local host without explicit opt-in., Return True if the host resolves to a loopback or unspecified address.      Ha, Raise if ``url`` is not safe to call by default.      Rules:     1. Must be a, UnsafeOllamaURLError, validate_ollama_base_url()

### Community 79 - "Run Paperplane"
Cohesion: 0.22
Nodes (7): Checks, Development, Important paths, Check and parse, Fastest option on Windows, Manual startup, Run Paperplane

### Community 80 - "Global Constraints"
Cohesion: 0.22
Nodes (8): Balanced PDF Latency Implementation Plan, Global Constraints, Task 1: Shared Balanced Job Deadline, Task 2: Stateless LangGraph Page Workflow, Task 3: Route V2 Page Processing Through the Workflow, Task 4: Latency and Model-Call Observability, Task 5: Balanced Cold-Cache Benchmark and Regression Gate, Task 6: Final Diff and Risk Review

### Community 81 - "Evidence Studio Design"
Cohesion: 0.22
Nodes (8): Architecture, Evidence Studio Design, Failure Handling, Goal, Product Direction, Responsive and Accessible Behavior, Verification, Workflow

### Community 82 - "Welcome to [Team Name]"
Cohesion: 0.22
Nodes (8): Codebases, Get Started, How We Use Claude, MCP Servers to Activate, Skills to Know About, Team Tips, Welcome to [Team Name], Your Setup Checklist

### Community 83 - "telemetry.py"
Cohesion: 0.29
Nodes (7): is_enabled(), OpenTelemetry setup for the extraction pipeline.  This module wires the OpenTe, Flush and shut down the tracer provider. Idempotent., Return True when telemetry setup is configured to run., Initialize OTel SDK + exporters. Idempotent.      Safe to call from the FastAP, setup_telemetry(), shutdown_telemetry()

### Community 84 - "CONTRIBUTING.md"
Cohesion: 0.25
Nodes (4): Reporting a Vulnerability, Response Process, Security Policy, Supported Versions

### Community 85 - "Contributing"
Cohesion: 0.25
Nodes (8): Before opening a PR, Changing parsing behavior, Code of conduct, Contributing, Ground rules, Local setup, Security, Where to start

### Community 86 - "FAQ"
Cohesion: 0.25
Nodes (8): Can I expose it on the internet?, Does it support background jobs or run history?, FAQ, Is OpenAI required?, Is Paperplane a Streamlit app?, Where are documents and results stored?, Which inputs are accepted?, Which model should I choose?

### Community 87 - "README.md"
Cohesion: 0.25
Nodes (6): Limitations, API, Paperplane, Processing flow, Run on Windows, Verify

### Community 88 - "Paperplane threat model"
Cohesion: 0.29
Nodes (6): Assets, Operational assumptions, Paperplane threat model, Principal threats and controls, Scope, Trust boundaries

### Community 89 - "OllamaReviewer"
Cohesion: 0.33
Nodes (5): OllamaReviewer, AsyncClient, Compare a rendered page against its Markdown without exposing cloud data., test_reviewer_rejects_unknown_region_ids(), test_reviewer_uses_qwen35_structured_vision_output()

### Community 90 - "Code of Conduct"
Cohesion: 0.29
Nodes (7): Code of Conduct, Enforcement, Enforcement Responsibilities, Our Pledge, Our Standards, Reporting, Scope

### Community 91 - "File Structure"
Cohesion: 0.29
Nodes (6): Dark Theme Implementation Plan, File Structure, Global Constraints, Task 1: Accessible persisted theme toggle, Task 2: Theme-aware visual tokens, Task 3: Final change review

### Community 92 - "Global Constraints"
Cohesion: 0.29
Nodes (6): Evidence Studio Implementation Plan, Global Constraints, Task 1: Lock the workspace contract with failing tests, Task 2: Build focused preview and history components, Task 3: Apply Graphite Signal and responsive layout, Task 4: Review, browser verification, and final push

### Community 93 - "Dark Theme Design"
Cohesion: 0.29
Nodes (6): Components and Behavior, Dark Theme Design, Failure Handling, Goal, Scope, Verification

### Community 94 - "Paperplane from zero to mastery"
Cohesion: 0.29
Nodes (5): Exercises, Mental model, Paperplane from zero to mastery, Trace the code, Study handbook moved

### Community 95 - "Release process"
Cohesion: 0.29
Nodes (7): 1. Versioning rules, 2. Branch and commit hygiene, 4. After the release, 5. Pre-release builds, 6. Hotfixes, 7. CI, Release process

### Community 96 - "3. Cutting a release"
Cohesion: 0.29
Nodes (7): 3.1 Decide the bump, 3.2 Run the release script (recommended), 3.3 Publish Python package (TestPyPI + PyPI), 3.4 Manual flow (small fixes only), 3. Cutting a release, One-time setup in package indexes, Verify published artifacts

### Community 97 - "require_rate_limit"
Cohesion: 0.33
Nodes (5): _identity(), Request, Return ``None`` if allowed, or seconds-until-reset if throttled., require_rate_limit(), test_identity_hash_is_stable_and_distinct_and_non_reversible()

### Community 98 - "FakeParser"
Cohesion: 0.47
Nodes (3): FakeParser, test_parse_is_stateless_and_returns_result_immediately(), test_parse_requires_openai_configuration()

### Community 99 - "[1.0.0] - 2026-07-23"
Cohesion: 0.33
Nodes (6): [1.0.0] - 2026-07-23, Added, Changed, Fixed, Migration, Removed

### Community 100 - "ADR 0001 — Record architecture decisions"
Cohesion: 0.33
Nodes (5): ADR 0001 — Record architecture decisions, Consequences, Context, Decision, Status

### Community 101 - "Paperplane capabilities"
Cohesion: 0.33
Nodes (5): Available, Deliberately absent, Models and modes, Output contract, Paperplane capabilities

### Community 102 - "MCP Tools: code-review-graph"
Cohesion: 0.40
Nodes (4): Key Tools, MCP Tools: code-review-graph, When to use graph tools FIRST, Workflow

### Community 103 - "MCP Tools: code-review-graph"
Cohesion: 0.40
Nodes (4): Key Tools, MCP Tools: code-review-graph, When to use graph tools FIRST, Workflow

### Community 104 - "Debug Issue"
Cohesion: 0.40
Nodes (4): Debug Issue, Steps, Tips, Token Efficiency Rules

### Community 105 - "Explore Codebase"
Cohesion: 0.40
Nodes (4): Explore Codebase, Steps, Tips, Token Efficiency Rules

### Community 106 - "Refactor Safely"
Cohesion: 0.40
Nodes (4): Refactor Safely, Safety Checks, Steps, Token Efficiency Rules

### Community 107 - "Review Changes"
Cohesion: 0.40
Nodes (4): Output Format, Review Changes, Steps, Token Efficiency Rules

### Community 108 - "MCP Tools: code-review-graph"
Cohesion: 0.40
Nodes (4): Key Tools, MCP Tools: code-review-graph, When to use graph tools FIRST, Workflow

### Community 109 - "Debug Issue"
Cohesion: 0.40
Nodes (4): Debug Issue, Steps, Tips, Token Efficiency Rules

### Community 110 - "Explore Codebase"
Cohesion: 0.40
Nodes (4): Explore Codebase, Steps, Tips, Token Efficiency Rules

### Community 111 - "Refactor Safely"
Cohesion: 0.40
Nodes (4): Refactor Safely, Safety Checks, Steps, Token Efficiency Rules

### Community 112 - "Review Changes"
Cohesion: 0.40
Nodes (4): Output Format, Review Changes, Steps, Token Efficiency Rules

### Community 113 - "Operations runbook"
Cohesion: 0.40
Nodes (4): Common failures, Health, Operations runbook, Restart and recovery

### Community 114 - "V2 Output Quality Implementation Plan"
Cohesion: 0.40
Nodes (4): Acceptance, Constraints, Tasks, V2 Output Quality Implementation Plan

### Community 115 - "MCP Tools: code-review-graph"
Cohesion: 0.40
Nodes (4): Key Tools, MCP Tools: code-review-graph, When to use graph tools FIRST, Workflow

### Community 116 - "Debug Issue"
Cohesion: 0.40
Nodes (4): Debug Issue, Steps, Tips, Token Efficiency Rules

### Community 117 - "Explore Codebase"
Cohesion: 0.40
Nodes (4): Explore Codebase, Steps, Tips, Token Efficiency Rules

### Community 118 - "Refactor Safely"
Cohesion: 0.40
Nodes (4): Refactor Safely, Safety Checks, Steps, Token Efficiency Rules

### Community 119 - "Review Changes"
Cohesion: 0.40
Nodes (4): Output Format, Review Changes, Steps, Token Efficiency Rules

### Community 120 - "MCP Tools: code-review-graph"
Cohesion: 0.40
Nodes (4): Key Tools, MCP Tools: code-review-graph, When to use graph tools FIRST, Workflow

### Community 121 - "MCP Tools: code-review-graph"
Cohesion: 0.40
Nodes (4): Key Tools, MCP Tools: code-review-graph, When to use graph tools FIRST, Workflow

### Community 122 - "MCP Tools: code-review-graph"
Cohesion: 0.40
Nodes (4): Key Tools, MCP Tools: code-review-graph, When to use graph tools FIRST, Workflow

### Community 123 - "Security best-practices review"
Cohesion: 0.40
Nodes (4): Current controls, Deployment requirements, Residual risks, Security best-practices review

### Community 124 - "[2.0.0] - 2026-07-26"
Cohesion: 0.50
Nodes (4): [2.0.0] - 2026-07-26, Added, Changed, Fixed

### Community 125 - "[Unreleased]"
Cohesion: 0.50
Nodes (4): Added, Changed, Fixed, [Unreleased]

### Community 126 - "ADR 0002 — Bounded page processing"
Cohesion: 0.50
Nodes (3): ADR 0002 — Bounded page processing, Decision, Status

### Community 127 - "ADR 0004 — Secure-by-default HTTP boundary"
Cohesion: 0.50
Nodes (3): ADR 0004 — Secure-by-default HTTP boundary, Decision, Status

## Knowledge Gaps
- **322 isolated node(s):** `uvx`, `crg-session-start.sh script`, `crg-update.sh script`, `uvx`, `uvx` (+317 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BoundingBox` connect `BoundingBox` to `LayoutEngine`, `schema_extraction.py`, `QualityScore`, `V2PageProcessor`, `evaluate_document`, `build_subdocument_payloads`, `GroundedChunk`, `Region`, `GlmOcrLayoutEngine`, `LayoutParser`, `.process_page`, `artifacts.py`, `DocumentInputError`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Why does `V2PageProcessor` connect `V2PageProcessor` to `GroundedChunk`, `v2_accuracy.py`, `.process_page`, `AgenticDocumentParser`, `main.py`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Why does `RenderedPage` connect `V2PageProcessor` to `LayoutEngine`, `PageResult`, `LayoutParser`, `.process_page`, `DocumentInputError`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Are the 40 inferred relationships involving `BoundingBox` (e.g. with `_region()` and `render_page()`) actually correct?**
  _`BoundingBox` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `V2PageProcessor` (e.g. with `lifespan()` and `AgenticDocumentParser`) actually correct?**
  _`V2PageProcessor` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `Region` (e.g. with `_region()` and `_layout()`) actually correct?**
  _`Region` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 46 inferred relationships involving `RenderedPage` (e.g. with `LayoutEngine` and `LayoutParser`) actually correct?**
  _`RenderedPage` has 46 INFERRED edges - model-reasoned connections that need verification._