# Graph Report - .  (2026-08-14)

## Corpus Check
- 289 files · ~149,931 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 163 nodes · 66 edges · 99 communities (14 shown, 85 thin omitted)
- Extraction: 64% EXTRACTED · 36% INFERRED · 0% AMBIGUOUS · INFERRED: 24 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Document Security Risks
- Vision Parsing Pipeline
- Local Parser Architecture
- Balanced Page Processing
- Evidence Grounding Runtime
- Document Intelligence Pipeline
- Debugging Agent Workflows
- Codebase Exploration Workflows
- Safe Refactoring Workflows
- Change Review Workflows
- Contribution Documentation
- Parser Design Decisions
- OCR Runtime Setup
- Extraction Prompt System
- Graph First Navigation
- Local Deployment Setup
- Version One Migration
- Operational Recovery Runbook
- Theme Implementation Plan
- Balanced Page Processing
- Output Quality Planning
- Dark Theme Design
- Evidence Studio Design
- Application Icon Design
- Graph Navigation Guidance
- Weekly Dependency Update Policy
- Continuous Integration
- Py PI Trusted Publishing
- Release Process
- Security Best-Practices Review
- V2 Pipeline Review Findings Tasks
- Project Agent Instructions
- Community Conduct Policy
- Postgres Service
- Architecture Document Redirect
- Pipeline Document Redirect
- Evidence Studio
- Upgrade Summary
- Application Icon
- Root Layout
- Artifact Gallery
- Document Inspector
- Review Workspace
- Schema Workspace
- Sub Document Gallery
- Document Source
- Run History
- Agentic Parse Artifact
- Agentic Parse Job
- Agentic Parse Settings
- Agent Trace Event
- Api Error
- Artifact Model
- Attempt Record
- create Evaluation Run
- create Job
- create Parse Batch
- create Parse Job
- Document Tree Item
- evaluate Job
- Evaluation Case
- Evaluation Run
- Expert Kind
- Extraction Schema
- Extraction Schema Validation
- Inspection Candidate
- Inspection Region
- Job Status
- Ollama Model
- Page Checkpoint
- Page Diagnostics
- Page Inspection
- Page Plan
- Parse Batch
- Parse Job
- Parse Model
- Parse Review
- Parse Settings
- Planning Mode
- Processing Stage
- Processing Strategy
- Quality Report
- Quality Score
- Quality Status
- Region Decision
- Region Observation
- Region Plan
- Region Type
- Reprocess Run
- Review Case
- Runtime Capabilities
- Sub Document
- Vision Model
- Vision Provider
- Visual Verification
- Bug Reproduction Template
- Feature Request Template
- Provider Integration Template
- Team Onboarding Guide

## God Nodes (most connected - your core abstractions)
1. `Security Threat Model` - 5 edges
2. `Parser Pipeline` - 5 edges
3. `LangGraph Parser StateGraph` - 4 edges
4. `Visual Verification and Repair` - 3 edges
5. `Paperplane Document Intelligence Pipeline` - 3 edges
6. `Debug Issue Workflow` - 2 edges
7. `Explore Codebase Workflow` - 2 edges
8. `Safe Refactoring Workflow` - 2 edges
9. `Change Review Workflow` - 2 edges
10. `Document Prompt Injection Risk` - 2 edges

## Surprising Connections (you probably didn't know these)
- `Debug Issue Workflow` --semantically_similar_to--> `Debug Issue Workflow`  [INFERRED] [semantically similar]
  .claude/skills/debug-issue/SKILL.md → .codebuddy/skills/debug-issue/SKILL.md
- `Debug Issue Workflow` --semantically_similar_to--> `Debug Issue Workflow`  [INFERRED] [semantically similar]
  .claude/skills/debug-issue/SKILL.md → .gemini/skills/debug-issue/SKILL.md
- `Explore Codebase Workflow` --semantically_similar_to--> `Explore Codebase Workflow`  [INFERRED] [semantically similar]
  .claude/skills/explore-codebase/SKILL.md → .codebuddy/skills/explore-codebase/SKILL.md
- `Explore Codebase Workflow` --semantically_similar_to--> `Explore Codebase Workflow`  [INFERRED] [semantically similar]
  .claude/skills/explore-codebase/SKILL.md → .gemini/skills/explore-codebase/SKILL.md
- `Safe Refactoring Workflow` --semantically_similar_to--> `Safe Refactoring Workflow`  [INFERRED] [semantically similar]
  .claude/skills/refactor-safely/SKILL.md → .codebuddy/skills/refactor-safely/SKILL.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Graph-Powered Engineering Workflows** — claude_skills_debug_issue_skill_debug_issue_workflow, claude_skills_explore_codebase_skill_explore_codebase_workflow, claude_skills_refactor_safely_skill_safe_refactoring_workflow, claude_skills_review_changes_skill_change_review_workflow, github_code_review_graph_instruction_graph_first_navigation [INFERRED 0.85]
- **Repository Quality Automation** — github_workflows_ci_continuous_integration, github_workflows_dependency_review_dependency_review, github_dependabot_dependency_update_policy, pre_commit_config_pre_commit_quality_gates [INFERRED 0.85]
- **Evidence Grounded V2 Extraction** — readme_paperplane_v2_runtime, prompts_v2_extraction_evidence_grounding, docs_zero_to_mastery_langgraph_agent [INFERRED 0.85]
- **Local-First Architecture** — docs_adr_0003_sqlite_wal_decision, docs_adr_0004_secure_default_controls, docs_deployment_local_runtime, docs_limitations_local_first_boundary [INFERRED 0.85]
- **Document Parsing Lifecycle** — docs_how_it_works_page_batch_processing, docs_how_it_works_paddleocr_vl, docs_how_it_works_glm_ocr, docs_how_it_works_visual_verification, docs_app_capabilities_grounded_markdown [EXTRACTED 1.00]
- **Paperplane Document Processing Flow** — docs_app_capabilities_layout_aware_markdown_reconstruction, docs_app_capabilities_zone_based_processing, docs_app_capabilities_langgraph_correction_loop [EXTRACTED 1.00]
- **Extraction Correction Prompts** — prompts_v1_extraction_structured_extraction, prompts_v1_reflection_self_refinement, prompts_v2_reflection_evidence_grounded_reflection [EXTRACTED 1.00]

## Communities (99 total, 85 thin omitted)

### Community 0 - "Document Security Risks"
Cohesion: 0.25
Nodes (8): Artifact Retention Risk, Optional API Key Cost Abuse, Document Prompt Injection Risk, Extraction Schema Authorization Bypass, Security Threat Model, Untrusted Document Ingest, Evidence-Grounded Extraction Pipeline, Release History

### Community 1 - "Vision Parsing Pipeline"
Cohesion: 0.25
Nodes (8): LangGraph over Bespoke Orchestrator, LangGraph Parser StateGraph, GLM-OCR Recognition Stage, PaddleOCR-VL Layout Processing, Recoverable Page Batch Processing, Visual Verification and Repair, OpenTelemetry Phoenix Tracing, Quality Evaluation Stack

### Community 2 - "Local Parser Architecture"
Cohesion: 0.29
Nodes (7): SQLite WAL Default Persistence, Secure-by-Default Controls, Grounded Markdown, Parse Job API, Parser Pipeline, Local-First Scope Boundary, MCP Extraction Tools

### Community 3 - "Balanced Page Processing"
Cohesion: 0.40
Nodes (5): Deadline Fallback, Balanced PDF Latency Design, Stateless Page Workflow, Paperplane Zero to Mastery, LangGraph Agent

### Community 4 - "Evidence Grounding Runtime"
Cohesion: 0.40
Nodes (5): V2 Evidence-Grounded Extraction Prompt, Evidence-Grounded Extraction, Paperplane README, Paperplane V2 Runtime, Processing Modes

### Community 5 - "Document Intelligence Pipeline"
Cohesion: 0.67
Nodes (4): LangGraph Correction Loop, Layout-Aware Markdown Reconstruction, Paperplane Document Intelligence Pipeline, Zone-Based Processing

### Community 6 - "Debugging Agent Workflows"
Cohesion: 0.67
Nodes (3): Debug Issue Workflow, Debug Issue Workflow, Debug Issue Workflow

### Community 7 - "Codebase Exploration Workflows"
Cohesion: 0.67
Nodes (3): Explore Codebase Workflow, Explore Codebase Workflow, Explore Codebase Workflow

### Community 8 - "Safe Refactoring Workflows"
Cohesion: 0.67
Nodes (3): Safe Refactoring Workflow, Safe Refactoring Workflow, Safe Refactoring Workflow

### Community 9 - "Change Review Workflows"
Cohesion: 0.67
Nodes (3): Change Review Workflow, Change Review Workflow, Change Review Workflow

### Community 10 - "Contribution Documentation"
Cohesion: 0.67
Nodes (3): Contribution Workflow, Architecture Decision Records, Local Development Workflow

### Community 11 - "Parser Design Decisions"
Cohesion: 0.67
Nodes (3): Parser Engine Routing, VLM As Extractor, Local-First Defaults

### Community 12 - "OCR Runtime Setup"
Cohesion: 0.67
Nodes (3): Self-Hosted OCR Setup Guide, GLM-OCR Setup, PaddleOCR-VL Setup

### Community 13 - "Extraction Prompt System"
Cohesion: 0.67
Nodes (3): Structured Extraction Prompt, Self-Refinement Prompt, Evidence-Grounded Reflection Prompt

## Knowledge Gaps
- **107 isolated node(s):** `RootLayout`, `ArtifactGallery`, `DocumentInspector`, `ReviewWorkspace`, `SchemaWorkspace` (+102 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **85 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Parser Pipeline` connect `Local Parser Architecture` to `Vision Parsing Pipeline`?**
  _High betweenness centrality (0.005) - this node is a cross-community bridge._
- **Why does `LangGraph Parser StateGraph` connect `Vision Parsing Pipeline` to `Local Parser Architecture`?**
  _High betweenness centrality (0.005) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Visual Verification and Repair` (e.g. with `LangGraph Parser StateGraph` and `Quality Evaluation Stack`) actually correct?**
  _`Visual Verification and Repair` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `RootLayout`, `ArtifactGallery`, `DocumentInspector` to the rest of the system?**
  _107 weakly-connected nodes found - possible documentation gaps or missing edges._