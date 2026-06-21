/** API client for backend communication. */

const API_BASE = "/api";

// ── Enums (mirrors backend app.models.enums) ────────────────────────

/** Local OCR/parser engine identifiers. */
export const ParserEngine = {
  AUTO: "auto",
  PADDLEOCR: "paddleocr",
  GLMOCR: "glmocr",
} as const;
export type ParserEngine = (typeof ParserEngine)[keyof typeof ParserEngine];

/** LLM provider identifiers. */
export const LLMProviderID = {
  AUTO: "auto",
  OPENAI: "openai",
  GEMINI: "gemini",
  ANTHROPIC: "anthropic",
} as const;
export type LLMProviderID = (typeof LLMProviderID)[keyof typeof LLMProviderID];

export const ProviderAvailabilityState = {
  READY: "ready",
  MISSING_API_KEY: "missing_api_key",
  CLIENT_NOT_INSTALLED: "client_not_installed",
  INVALID_API_KEY: "invalid_api_key",
  LISTING_UNSUPPORTED: "listing_unsupported",
  ERROR: "error",
} as const;
export type ProviderAvailabilityState =
  (typeof ProviderAvailabilityState)[keyof typeof ProviderAvailabilityState];

export const ModelCatalogSource = {
  DYNAMIC: "dynamic",
  PLACEHOLDER: "placeholder",
} as const;
export type ModelCatalogSource =
  (typeof ModelCatalogSource)[keyof typeof ModelCatalogSource];

/** Model selection mode identifiers. */
export const ModelSelectionMode = {
  AUTO: "auto",
  EXPLICIT_MODEL_ID: "explicit_model_id",
} as const;
export type ModelSelectionMode =
  (typeof ModelSelectionMode)[keyof typeof ModelSelectionMode];

/** Extraction job lifecycle statuses. */
export const ExtractionStatus = {
  PENDING: "pending",
  QUEUED: "queued",
  PROCESSING: "processing",
  OCR_COMPLETE: "ocr_complete",
  EXTRACTED: "extracted",
  COMPLETED: "completed",
  NEEDS_REVIEW: "needs_review",
  FAILED: "failed",
} as const;
export type ExtractionStatus =
  (typeof ExtractionStatus)[keyof typeof ExtractionStatus];

/** Extraction field data types. */
export const FieldType = {
  STRING: "string",
  NUMBER: "number",
  BOOLEAN: "boolean",
  DATE: "date",
  LIST: "list",
  OBJECT: "object",
} as const;
export type FieldType = (typeof FieldType)[keyof typeof FieldType];

/** Review decision identifiers. */
export const ReviewDecision = {
  APPROVED: "approved",
  CORRECTED: "corrected",
  REJECTED: "rejected",
} as const;
export type ReviewDecision =
  (typeof ReviewDecision)[keyof typeof ReviewDecision];

export const ReviewVerdict = {
  VALID: "valid",
  NEEDS_REVIEW: "needs_review",
  APPROVED: "approved",
  CORRECTED: "corrected",
  REJECTED: "rejected",
} as const;
export type ReviewVerdict =
  (typeof ReviewVerdict)[keyof typeof ReviewVerdict];

// ── Interfaces ──────────────────────────────────────────────────────

export interface DocumentResponse {
  id: string;
  filename: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  page_count: number | null;
  status: string;
  created_at: string;
}

export interface SchemaFieldDef {
  name: string;
  description: string;
  field_type: FieldType;
  required: boolean;
}

export interface ExtractionSchemaResponse {
  id: string;
  name: string;
  description: string | null;
  fields: SchemaFieldDef[];
  created_at: string;
  updated_at: string;
}

export interface ValidationResultInfo {
  field_name: string | null;
  valid: boolean;
  message: string;
}

export interface ExtractionStepInfo {
  name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  error: string | null;
}

export interface ReviewInfo {
  id: number;
  extraction_id: string;
  decision: ReviewDecision;
  corrected_fields: Record<string, unknown> | null;
  notes: string | null;
  created_at: string;
}

export interface ReviewCreate {
  decision: ReviewDecision;
  corrected_fields?: Record<string, unknown> | null;
  notes?: string | null;
}

export interface ExtractionResponse {
  id: string;
  document_id: string;
  schema_id: string;
  ocr_provider: ParserEngine;
  llm_provider: LLMProviderID;
  llm_model: string;
  status: ExtractionStatus;
  ocr_text: string | null;
  result: Record<string, unknown> | null;
  validation_errors: string[] | null;
  validation_results: ValidationResultInfo[] | null;
  review_verdict: ReviewVerdict | null;
  error: string | null;
  ocr_provider_used: string | null;
  llm_provider_used: string | null;
  llm_model_used: string | null;
  confidence: Record<string, number> | null;
  extract_attempts: number | null;
  error_category: string | null;
  steps: ExtractionStepInfo[];
  reviews: ReviewInfo[];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  reviewed_at: string | null;
  duration_total_ms: number | null;
  validation_summary: string | null;
}

export interface ParserOptionInfo {
  id: ParserEngine;
  name: string;
  enabled: boolean;
  available: boolean;
}

export interface ExtractionResultResponse {
  extraction_id: string;
  status: ExtractionStatus;
  result: Record<string, unknown> | null;
  ocr_provider_used: string | null;
  llm_provider_used: string | null;
  llm_model_used: string | null;
  completed_at: string | null;
}

export interface ExtractionValidationResponse {
  extraction_id: string;
  status: ExtractionStatus;
  validation_errors: string[];
  validation_results: ValidationResultInfo[] | null;
  review_verdict: ReviewVerdict | null;
  completed_at: string | null;
}

export interface ProviderErrorState {
  code: string;
  message: string;
  retryable: boolean;
}

export interface ProviderAvailabilityStatus {
  state: ProviderAvailabilityState;
  configured: boolean;
  available: boolean;
  can_extract: boolean;
  can_list_models: boolean;
  auto_eligible: boolean;
}

export interface LLMProviderInfo {
  id: LLMProviderID;
  name: string;
  available: boolean;
  availability: ProviderAvailabilityStatus;
  error: ProviderErrorState | null;
  is_default: boolean;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: LLMProviderID;
  is_default: boolean;
}

export interface LLMModelListResponse {
  provider_id: LLMProviderID;
  provider_name: string;
  available: boolean;
  source: ModelCatalogSource;
  availability: ProviderAvailabilityStatus;
  models: ModelInfo[];
  error: ProviderErrorState | null;
  resolved_provider_id: LLMProviderID | null;
}

export interface OCREngineFlags {
  paddleocr: boolean;
  glm_ocr: boolean;
}

export interface AppConfigResponse {
  parser_engines: ParserEngine[];
  llm_providers: LLMProviderID[];
  default_llm_provider: LLMProviderID;
  model_selection_modes: ModelSelectionMode[];
  ocr_engine_flags: OCREngineFlags;
  max_upload_size_mb: number;
  supported_file_types: string[];
  confidence_threshold: number;
}

export interface CreateSchemaRequest {
  name: string;
  description?: string;
  fields: SchemaFieldDef[];
}

export interface CreateSchemaFromPresetRequest {
  name?: string | null;
}

export interface StartExtractionRequest {
  document_id: string;
  schema_id: string;
  ocr_provider?: ParserEngine;
  llm_provider?: LLMProviderID;
  llm_model?: string;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const validationLines = detail
      .map((entry) => {
        if (!entry || typeof entry !== "object") return null;
        const maybeLoc = "loc" in entry ? (entry as { loc?: unknown }).loc : undefined;
        const maybeMsg = "msg" in entry ? (entry as { msg?: unknown }).msg : undefined;
        if (typeof maybeMsg !== "string") return null;
        const location = Array.isArray(maybeLoc)
          ? maybeLoc.filter((part) => typeof part === "string" || typeof part === "number").join(".")
          : null;
        return location ? `${location}: ${maybeMsg}` : maybeMsg;
      })
      .filter((line): line is string => Boolean(line));
    if (validationLines.length > 0) {
      return validationLines.join("; ");
    }
  }
  return "Request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { headers, cache, ...rest } = init ?? {};
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    cache: cache ?? "no-store",
    headers: {
      ...(headers ?? {}),
      ...(rest.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    throw new ApiError(
      res.status,
      formatErrorDetail(detail) || `HTTP ${res.status}`,
      detail,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// Documents
export const uploadDocument = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<DocumentResponse>("/documents/", { method: "POST", body: form });
};
export const listDocuments = () =>
  request<DocumentResponse[]>("/documents/");
export const getDocument = (id: string) =>
  request<DocumentResponse>(`/documents/${encodeURIComponent(id)}`);

// Schemas
export const createSchema = (data: {
  name: string;
  description?: string;
  fields: SchemaFieldDef[];
}) => request<ExtractionSchemaResponse>("/schemas/", { method: "POST", body: JSON.stringify(data) });
export const listSchemas = () =>
  request<ExtractionSchemaResponse[]>("/schemas/");

const _schemaCache = new Map<string, ExtractionSchemaResponse>();

export const getSchema = async (id: string): Promise<ExtractionSchemaResponse> => {
  const cached = _schemaCache.get(id);
  if (cached) return cached;
  const schema = await request<ExtractionSchemaResponse>(
    `/schemas/${encodeURIComponent(id)}`,
  );
  _schemaCache.set(id, schema);
  return schema;
};

export interface SchemaPreset {
  id: string;
  name: string;
  description: string;
  doc_type: string;
  fields: SchemaFieldDef[];
}
export const getSchemaPresets = () =>
  request<SchemaPreset[]>("/schemas/presets", { cache: "force-cache" });
export const createSchemaFromPreset = (presetId: string, name?: string) =>
  request<ExtractionSchemaResponse>(`/schemas/presets/${encodeURIComponent(presetId)}`, {
    method: "POST",
    body: JSON.stringify({ name: name || undefined }),
  });

// Extractions
export const startExtraction = (data: StartExtractionRequest) =>
  request<ExtractionResponse>("/extractions/", {
    method: "POST",
    body: JSON.stringify(data),
  });
export const listExtractions = (documentId?: string) => {
  const qs = documentId ? `?document_id=${encodeURIComponent(documentId)}` : "";
  return request<ExtractionResponse[]>(`/extractions/${qs}`);
};
export const getExtraction = (id: string) =>
  request<ExtractionResponse>(`/extractions/${encodeURIComponent(id)}`);
export const retryExtraction = (id: string) =>
  request<ExtractionResponse>(`/extractions/${encodeURIComponent(id)}/retry`, {
    method: "POST",
  });

// Providers
export const getParsers = () =>
  request<ParserOptionInfo[]>("/providers/parsers");
export const getLLMProviders = () =>
  request<LLMProviderInfo[]>('/providers/llm');
export const getLLMModels = (providerId: string) =>
  request<LLMModelListResponse>(`/providers/llm/${encodeURIComponent(providerId)}/models`);

// App config (non-secret settings for UI)
export const getAppConfig = () =>
  request<AppConfigResponse>("/providers/config", { cache: "force-cache" });

// Extraction sub-endpoints
export const getExtractionResult = (id: string) =>
  request<ExtractionResultResponse>(`/extractions/${encodeURIComponent(id)}/result`);
export const getExtractionValidation = (id: string) =>
  request<ExtractionValidationResponse>(`/extractions/${encodeURIComponent(id)}/validation`);

// Reviews
export const submitReview = (id: string, data: ReviewCreate) =>
  request<ReviewInfo>(`/extractions/${encodeURIComponent(id)}/reviews`, {
    method: "POST",
    body: JSON.stringify(data),
  });
export const listReviews = (id: string) =>
  request<ReviewInfo[]>(`/extractions/${encodeURIComponent(id)}/reviews`);

// ── Display names (shared across UI) ────────────────────────────────

/** Human-friendly labels for provider/parser IDs shown in the UI. */
export const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  auto: "Auto",
  pymupdf: "Built-in PDF reader (PyMuPDF)",
  paddleocr: "PaddleOCR (local image OCR)",
  glmocr: "GLM-OCR (local Ollama)",
  openai: "OpenAI",
  gemini: "Gemini",
  anthropic: "Anthropic Claude",
};

/** Resolve a provider/parser ID to its display name. */
export function displayName(id: string): string {
  return PROVIDER_DISPLAY_NAMES[id] ?? id;
}

function normalizeSelection(value: string | null | undefined): string | null {
  if (!value) return null;
  const normalized = value.trim();
  return normalized ? normalized : null;
}

/**
 * Build a display string for a provider field that was potentially auto-resolved.
 *
 * - User chose Auto and it resolved → "Auto → OpenAI"
 * - User chose Auto but job hasn't resolved yet → "Auto"
 * - User explicitly chose a provider → "OpenAI"
 */
export function resolvedDisplayName(
  requested: string,
  actual: string | null,
): string {
  const requestedValue = normalizeSelection(requested);
  const actualValue = normalizeSelection(actual);

  if (!requestedValue && !actualValue) return "\u2014";
  if (!actualValue) return displayName(requestedValue ?? "auto");
  if (!requestedValue || actualValue === requestedValue) {
    return displayName(actualValue);
  }
  return `${displayName(requestedValue)} \u2192 ${displayName(actualValue)}`;
}

export function displayModelName(modelId: string | null | undefined): string {
  const normalized = normalizeSelection(modelId);
  if (!normalized) return "\u2014";
  if (normalized === "auto") return "Auto";
  return normalized;
}

export function resolvedModelDisplayName(
  requested: string | null | undefined,
  actual: string | null,
): string {
  const requestedValue = normalizeSelection(requested);
  const actualValue = normalizeSelection(actual);

  if (!requestedValue && !actualValue) return "\u2014";
  if (!actualValue) return displayModelName(requestedValue);
  if (!requestedValue || actualValue === requestedValue) {
    return displayModelName(actualValue);
  }
  return `${displayModelName(requestedValue)} \u2192 ${displayModelName(actualValue)}`;
}

// ── Error category labels ───────────────────────────────────────────

const ERROR_CATEGORY_LABELS: Record<string, { label: string; hint: string }> = {
  auth: { label: "Authentication", hint: "API key is missing or invalid" },
  rate_limit: { label: "Rate limited", hint: "Provider quota exceeded — try again later" },
  timeout: { label: "Timed out", hint: "The operation took too long" },
  parse_error: { label: "Parse error", hint: "AI returned malformed output" },
  provider_error: { label: "Provider error", hint: "The AI provider returned an error" },
  file_error: { label: "File error", hint: "The input file could not be read" },
  validation: { label: "Validation", hint: "Validation or reviewer feedback blocked this extraction" },
  unknown: { label: "Error", hint: "An unexpected error occurred" },
};

export function errorCategoryLabel(category: string | null): { label: string; hint: string } | null {
  if (!category) return null;
  return ERROR_CATEGORY_LABELS[category] ?? { label: category, hint: "" };
}

// ── Relative time ───────────────────────────────────────────────────

export function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
