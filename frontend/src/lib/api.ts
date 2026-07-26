const API_BASE = "/api";

export type JobStatus =
  | "queued" | "inspecting" | "processing" | "assembling" | "cancelling"
  | "cancelled" | "paused" | "completed" | "completed_with_warnings" | "failed";

export interface ParseSettings {
  segment_documents: boolean;
  document_profile: "auto" | "technical_document" | "scientific_paper" | "invoice" | "insurance_claim" | "healthcare_form" | "general_scanned";
  structured_extraction: boolean;
  allow_sensitive_cloud: boolean;
  processing_mode: "local_only" | "hybrid" | "maximum_accuracy";
  quality_overrides: Partial<Record<"min_region_confidence" | "min_overall" | "min_extraction_accuracy" | "min_structural_fidelity" | "min_completeness" | "min_markdown_consistency" | "min_table_integrity" | "min_citation_coverage" | "max_repairs", number>>;
  ocr_provider: "ollama" | "openai" | "anthropic" | "gemini" | "xai";
  ocr_model: string | null;
  review_provider: "ollama" | "openai" | "anthropic" | "gemini" | "xai";
  review_model: string | null;
  extraction_schema_id: string | null;
  extraction_provider: "ollama" | "openai" | "anthropic" | "gemini" | "xai";
  extraction_model: string | null;
  cloud_mode: "off" | "adaptive" | "all_pages";
  blind_local_retry: boolean;
  start_page: number;
  end_page: number | null;
  input_mode: "scanned" | "native" | "mixed";
  dpi: 150 | 200 | 300;
  marginalia_policy: "remove_repeated" | "keep_all";
  describe_figures: boolean;
  grounding_pdf: boolean;
  searchable_pdf: boolean;
  bundle: boolean;
}

export interface ExtractionSchema {
  id: string;
  name: string;
  description: string | null;
  version: number;
  json_schema: Record<string, unknown>;
  schema_sha256: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExtractionSchemaValidation {
  valid: boolean;
  normalized_schema: Record<string, unknown> | null;
  errors: Array<{ path: string; code: string; message: string }>;
}

export interface RuntimeCapabilities {
  paddleocr_vl_available: boolean;
  parser_model: string;
  pipeline_version: string;
  paddleocr_vl: {
    available: boolean;
    docker_available: boolean;
    gpu_available: boolean;
    image_present: boolean;
    cache_ready: boolean;
    image: string;
    error: string | null;
    pull_command: string | null;
  };
  providers: VisionProvider[];
}

export interface VisionModel { id: string; name: string }
export interface VisionProvider {
  id: ParseSettings["ocr_provider"];
  name: string;
  state: "ready" | "not_configured" | "unavailable";
  models: VisionModel[];
}

export interface PageCheckpoint {
  page_number: number;
  status: string;
  routing: string | null;
  warnings: string[];
  error_code: string | null;
  error_message: string | null;
  attempts: number;
  duration_ms: number | null;
  stage: ProcessingStage | null;
  quality_status: QualityStatus | null;
  quality_score: number | null;
  repair_count: number;
  diagnostics_url: string | null;
}

export type PlanningMode = "page_centric" | "two_pass_document";
export type ProcessingStrategy = "native" | "ocr" | "specialist" | "fallback";
export type ExpertKind = "text" | "table" | "chart" | "figure" | "formula" | "fallback";
export type QualityStatus = "pass" | "warn" | "fail";
export type ProcessingStage = "inspecting" | "planning" | "processing" | "scoring" | "verifying" | "repairing" | "completed";
export type RegionType = "title" | "heading" | "text" | "list" | "table" | "chart" | "formula" | "figure" | "header" | "footer" | "page_number" | "code" | "quote" | "form_field" | "checkbox" | "signature" | "seal";

export interface QualityScore {
  extraction_accuracy: number;
  structural_fidelity: number;
  completeness: number;
  markdown_consistency: number;
  overall: number;
  reasons: string[];
}

export interface RegionObservation {
  region_id: string;
  region_type: RegionType;
  bbox: { left: number; top: number; right: number; bottom: number };
  native_healthy: boolean;
  confidence: number | null;
  risk_flags: string[];
}

export interface RegionPlan {
  region_id: string;
  strategy: ProcessingStrategy;
  expert: ExpertKind;
  difficulty: number;
  risk_flags: string[];
  prompt_variant: string;
}

export interface PagePlan {
  page_number: number;
  source: "model" | "deterministic";
  regions: RegionPlan[];
  warnings: string[];
}

export interface AttemptRecord {
  attempt: number;
  strategy: ProcessingStrategy;
  expert: ExpertKind;
  prompt_id: string;
  prompt_version: string;
  prompt_variant: string;
  source: string;
  model: string | null;
  score: QualityScore;
  verdict: QualityStatus;
  reason: string;
  repair_hint: string | null;
  warnings: string[];
  latency_ms: number;
  eval_count: number | null;
  prompt_eval_count: number | null;
}

export interface RegionDecision {
  observation: RegionObservation;
  plan: RegionPlan;
  attempts: AttemptRecord[];
  selected_attempt_index: number;
  final_status: QualityStatus;
  visual_verification: VisualVerification | null;
}

export interface VisualVerification {
  region_id: string;
  bbox: { left: number; top: number; right: number; bottom: number };
  status: QualityStatus;
  methods: Array<"local_coordinate" | "cloud_visual">;
  reasons: string[];
}

export interface PageDiagnostics {
  schema_version: "1";
  planning_mode: PlanningMode;
  stage: ProcessingStage;
  page_number: number;
  plan: PagePlan | null;
  region_decisions: RegionDecision[];
  quality_score: QualityScore | null;
  quality_status: QualityStatus;
  repair_count: number;
  warnings: string[];
  fingerprint: string;
}

export interface Artifact {
  id: string;
  type: string;
  region_id: string | null;
  mime_type: string;
  size: number;
  sha256: string;
  filename: string;
  download_url: string;
  preview_url: string | null;
}

export interface ParseJob {
  id: string;
  original_filename: string;
  source_size: number;
  page_count: number;
  status: JobStatus;
  settings: ParseSettings;
  current_page: number | null;
  current_batch: number | null;
  total_batches: number;
  detected_profile: string | null;
  profile_confidence: number | null;
  segmentation_status: string;
  subdocument_count: number;
  is_partial: boolean;
  completed_pages: number;
  failed_pages: number;
  warning_count: number;
  review_required_count: number;
  quality_policy: Record<string, unknown> | null;
  error_message: string | null;
  model_name: string | null;
  model_digest: string | null;
  review_model_name: string | null;
  review_model_digest: string | null;
  extraction_schema: { id: string; name: string; version: number; schema_sha256: string } | null;
  extraction_model_name: string | null;
  extraction_model_digest: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  pages: PageCheckpoint[];
  artifacts: Artifact[];
  source_preview_url: string;
  output_revision: number;
  verified_export_ready: boolean;
  batch_id: string | null;
  batch_ordinal: number | null;
}

export interface InspectionCandidate { id: string; attempt: number; source: string; model: string | null; output: string; selected: boolean; verdict: string; reason: string; confidence: number | null; latency_ms: number | null; warnings: string[]; }
export interface InspectionRegion { id: string; type: string; bbox: { x0: number; y0: number; x1: number; y1: number }; order: number; confidence: number | null; source: string; source_label: string | null; content: string; markdown: string; parent_id: string | null; warnings: string[]; quality_status: string | null; candidates: InspectionCandidate[]; }
export interface PageInspection { page_number: number; width: number; height: number; coordinate_unit: string; image_url: string; quality_status: string | null; quality_score: Record<string, number> | null; reviewer: { provider: string | null; model: string | null; enabled: boolean }; warnings: string[]; regions: InspectionRegion[]; }
export interface DocumentTreeItem { id: string; page: number; order: number; type: string; content: string; summary: string; parent_id: string | null; heading_path: string[]; bbox: InspectionRegion["bbox"]; source: string; confidence: number | null; warnings: string[]; }
export interface QualityReport { processed_pages: number; ocr_coverage: { covered_regions: number; total_regions: number; ratio: number }; disagreements: Array<{ page: number; region_id: string; candidate_count: number }>; unresolved_regions: Array<{ page: number; region_id: string; status: string; type: string }>; source_counts: Record<string, number>; table_integrity: { passing_tables: number; total_tables: number; ratio: number; evaluated_accuracy: number | null }; warnings: string[]; verified_export_ready: boolean; }
export interface ReprocessRun { id: string; job_id: string; target_kind: "page" | "region"; page_number: number; region_id: string | null; dpi: number; crop_padding: number; status: string; decision: Record<string, unknown> | null; error_message: string | null; }
export interface ParseBatch { id: string; status: string; total_jobs: number; completed_jobs: number; failed_jobs: number; cancelled_jobs: number; bundle_ready: boolean; bundle_url: string | null; created_at: string | null; completed_at: string | null; jobs: ParseJob[]; }

export interface SubDocument {
  id: string;
  ordinal: number;
  start_page: number;
  end_page: number;
  profile: string;
  confidence: number;
  identifiers: Array<{ kind: string; value?: string; normalized_value: string; page?: number }>;
  boundary_confidence: number;
  boundary_reasons: string[];
  complete: boolean;
  missing_pages: number[];
  warnings: string[];
  artifacts: Artifact[];
}

export interface ReviewCase {
  id: string; job_id: string; item_kind: string; item_key: string;
  page_number: number | null; severity: string; status: string;
  failure_codes: string[]; original: Record<string, unknown>;
  current: Record<string, unknown>; provenance: Record<string, unknown>; revision: number;
}

export interface EvaluationCase {
  id: string;
  external_id: string;
  parse_job_id: string;
  status: string;
  metrics: Record<string, number> | null;
  error_message: string | null;
  report_url: string | null;
}

export interface EvaluationRun {
  id: string;
  kind: "single" | "batch";
  status: string;
  settings: Record<string, unknown>;
  metrics: Record<string, number> | null;
  total_cases: number;
  completed_cases: number;
  failed_cases: number;
  error_message: string | null;
  report_url: string | null;
  cases: EvaluationCase[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(
      0,
      "Paperplane backend is unavailable. Start FastAPI and confirm the frontend backend URL and port.",
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail;
    const message = typeof detail === "string"
      ? detail
      : typeof detail?.message === "string"
        ? detail.message
        : response.status >= 500
          ? "Paperplane backend is unavailable. Start FastAPI and confirm the frontend backend URL and port."
          : `Request failed (${response.status})`;
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? undefined as T : response.json();
}

export const listJobs = async () => (await request<{ items: ParseJob[] }>("/parse-jobs")).items;
export const listParseBatches = async () => (await request<{ items: ParseBatch[] }>("/parse-batches")).items;
export const getParseBatch = (id: string) => request<ParseBatch>(`/parse-batches/${encodeURIComponent(id)}`);
export const getPageInspection = (jobId: string, page: number, signal?: AbortSignal) => request<PageInspection>(`/parse-jobs/${encodeURIComponent(jobId)}/pages/${page}/inspection`, { signal });
export const getDocumentTree = async (jobId: string, query = "", signal?: AbortSignal) => (await request<{ items: DocumentTreeItem[] }>(`/parse-jobs/${encodeURIComponent(jobId)}/document-tree?q=${encodeURIComponent(query)}`, { signal })).items;
export const getQualityReport = (jobId: string, signal?: AbortSignal) => request<QualityReport>(`/parse-jobs/${encodeURIComponent(jobId)}/quality-report`, { signal });
export const requestReprocess = (jobId: string, body: { target_kind: "page" | "region"; page_number: number; region_id?: string; dpi: 150 | 200 | 300; crop_padding: 0 | 0.05 | 0.1 | 0.2 }) => request<ReprocessRun>(`/parse-jobs/${encodeURIComponent(jobId)}/reprocess`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const listExtractionSchemas = async () =>
  (await request<{ items: ExtractionSchema[] }>("/extraction-schemas")).items;
export const validateExtractionSchema = (json_schema: Record<string, unknown>) =>
  request<ExtractionSchemaValidation>("/extraction-schemas/validate", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ json_schema }),
  });
export const createExtractionSchema = (body: { name: string; description: string | null; json_schema: Record<string, unknown> }) =>
  request<ExtractionSchema>("/extraction-schemas", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
export const updateExtractionSchema = (id: string, body: { name: string; description: string | null; json_schema: Record<string, unknown> }) =>
  request<ExtractionSchema>(`/extraction-schemas/${encodeURIComponent(id)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
export const deleteExtractionSchema = (id: string) =>
  request<void>(`/extraction-schemas/${encodeURIComponent(id)}`, { method: "DELETE" });
export interface OllamaModel {
  name: string;
  digest: string | null;
  size: number | null;
  modified_at: string | null;
  capabilities: string[];
  compatible: boolean;
  inspection_error: string | null;
}
export const listOllamaModels = async (refresh = false) =>
  (await request<{ models: OllamaModel[] }>(`/ollama/models${refresh ? "?refresh=true" : ""}`)).models;
export const getJob = (id: string, signal?: AbortSignal) => request<ParseJob>(`/parse-jobs/${id}`, { signal });
export const getRuntimeCapabilities = () =>
  request<RuntimeCapabilities>("/runtime/capabilities");
export const cancelJob = (id: string) =>
  request<ParseJob>(`/parse-jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
export const getPageDiagnostics = (jobId: string, pageNumber: number, signal?: AbortSignal) =>
  request<PageDiagnostics>(`/parse-jobs/${encodeURIComponent(jobId)}/pages/${pageNumber}/diagnostics`, { signal });
export const listSubdocuments = async (jobId: string, signal?: AbortSignal) =>
  (await request<{ items: SubDocument[] }>(`/parse-jobs/${encodeURIComponent(jobId)}/sub-documents`, { signal })).items;

export async function createJob(file: File, settings: ParseSettings): Promise<ParseJob> {
  const form = new FormData();
  form.append("file", file);
  form.append("settings", JSON.stringify(settings));
  return request<ParseJob>("/parse-jobs", { method: "POST", body: form });
}

export async function createParseBatch(files: File[], settings: ParseSettings): Promise<ParseBatch> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("settings", JSON.stringify(settings));
  return request<ParseBatch>("/parse-batches", { method: "POST", body: form });
}

export async function evaluateJob(jobId: string, gold: File): Promise<EvaluationRun> {
  const form = new FormData();
  form.append("gold", gold);
  return request<EvaluationRun>(`/evaluation-runs/from-job/${encodeURIComponent(jobId)}`, {
    method: "POST",
    body: form,
  });
}

export async function createEvaluationRun(dataset: File, settings: ParseSettings): Promise<EvaluationRun> {
  const form = new FormData();
  form.append("dataset", dataset);
  form.append("settings", JSON.stringify(settings));
  return request<EvaluationRun>("/evaluation-runs", { method: "POST", body: form });
}

export const listEvaluationRuns = async () => {
  const response = await request<{ items: EvaluationRun[] }>("/evaluation-runs");
  return response.items;
};

export const getEvaluationRun = (runId: string, signal?: AbortSignal) =>
  request<EvaluationRun>(`/evaluation-runs/${encodeURIComponent(runId)}`, { signal });

export const listReviewCases = async (status = "open") =>
  (await request<{ items: ReviewCase[] }>(`/review-cases?status=${encodeURIComponent(status)}`)).items;
export const decideReviewCase = (id: string, body: Record<string, unknown>) =>
  request<ReviewCase>(`/review-cases/${encodeURIComponent(id)}/decisions`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
export const approveCuratedDocument = (jobId: string) =>
  request<Record<string, unknown>>(`/curation/documents/${encodeURIComponent(jobId)}/approve`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  });

export const apiResourceUrl = (path: string) => `${API_BASE.replace(/\/$/, "")}${path.replace(/^\/api/, "")}`;
export const artifactUrl = (artifact: Pick<Artifact, "download_url">) => apiResourceUrl(artifact.download_url);
export const getMarkdown = async (artifact: Pick<Artifact, "download_url">, signal?: AbortSignal) => {
  const response = await fetch(artifactUrl(artifact), { cache: "no-store", signal });
  if (!response.ok) throw new Error("Markdown is not available yet");
  return response.text();
};
