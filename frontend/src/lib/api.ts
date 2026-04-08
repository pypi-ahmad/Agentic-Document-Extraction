/** API client for backend communication. */

const API_BASE = "/api";

// ── Enums (mirrors backend app.models.enums) ────────────────────────

/** Local OCR/parser engine identifiers. */
export const ParserEngine = {
  AUTO: "auto",
  PADDLEOCR: "paddleocr",
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
  ocr_provider: string;
  llm_provider: string;
  llm_model: string;
  status: string;
  ocr_text: string | null;
  result: Record<string, unknown> | null;
  validation_errors: string[] | null;
  validation_results: Record<string, unknown>[] | null;
  review_verdict: string | null;
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
  id: string;
  name: string;
  enabled: boolean;
  available: boolean;
}

export interface ExtractionResultResponse {
  extraction_id: string;
  status: string;
  result: Record<string, unknown> | null;
  ocr_provider_used: string | null;
  llm_provider_used: string | null;
  llm_model_used: string | null;
  completed_at: string | null;
}

export interface ExtractionValidationResponse {
  extraction_id: string;
  status: string;
  validation_errors: string[];
  validation_results: Record<string, unknown>[] | null;
  review_verdict: string | null;
  completed_at: string | null;
}

export interface ProviderInfo {
  id: string;
  name: string;
  available: boolean;
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
  id: string;
  name: string;
  available: boolean;
  availability: ProviderAvailabilityStatus;
  error: ProviderErrorState | null;
  is_default: boolean;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  is_default: boolean;
}

export interface LLMModelListResponse {
  provider_id: string;
  provider_name: string;
  available: boolean;
  source: ModelCatalogSource;
  availability: ProviderAvailabilityStatus;
  models: ModelInfo[];
  error: ProviderErrorState | null;
  resolved_provider_id: string | null;
}

export interface OCREngineFlags {
  paddleocr: boolean;
}

export interface AppConfigResponse {
  parser_engines: ParserEngine[];
  llm_providers: LLMProviderID[];
  default_llm_provider: LLMProviderID;
  model_selection_modes: ModelSelectionMode[];
  ocr_engine_flags: OCREngineFlags;
  max_upload_size_mb: number;
  supported_file_types: string[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      ...(init?.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
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

// Schema presets
export interface SchemaPresetField {
  name: string;
  description: string;
  field_type: string;
  required: boolean;
}
export interface SchemaPreset {
  id: string;
  name: string;
  description: string;
  doc_type: string;
  fields: SchemaPresetField[];
}
export const getSchemaPresets = () =>
  request<SchemaPreset[]>("/schemas/presets");
export const createSchemaFromPreset = (presetId: string, name?: string) =>
  request<ExtractionSchemaResponse>("/schemas/from-preset", {
    method: "POST",
    body: JSON.stringify({ preset_id: presetId, name: name || undefined }),
  });

// Extractions
export const startExtraction = (data: {
  document_id: string;
  schema_id: string;
  ocr_provider?: ParserEngine;
  llm_provider?: LLMProviderID;
  llm_model?: string;
}) =>
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
export const getOCRProviders = () =>
  request<ProviderInfo[]>("/providers/ocr");
export const getParsers = () =>
  request<ParserOptionInfo[]>("/providers/parsers");
export const getLLMProviders = () =>
  request<LLMProviderInfo[]>('/providers/llm');
export const getLLMModels = (providerId: string) =>
  request<LLMModelListResponse>(`/providers/llm/${encodeURIComponent(providerId)}/models`);

// App config (non-secret settings for UI)
export const getAppConfig = () =>
  request<AppConfigResponse>("/providers/config");

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
  pymupdf: "PyMuPDF",
  paddleocr: "PaddleOCR",
  openai: "OpenAI",
  gemini: "Gemini",
  anthropic: "Anthropic",
};

/** Resolve a provider/parser ID to its display name. */
export function displayName(id: string): string {
  return PROVIDER_DISPLAY_NAMES[id] ?? id;
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
  if (actual) {
    // Auto resolved to a concrete provider
    if (requested === "auto" && actual !== "auto") {
      return `Auto \u2192 ${displayName(actual)}`;
    }
    return displayName(actual);
  }
  // Not yet resolved — show what was requested
  return displayName(requested);
}

// ── Error category labels ───────────────────────────────────────────

const ERROR_CATEGORY_LABELS: Record<string, { label: string; hint: string }> = {
  auth: { label: "Authentication", hint: "API key is missing or invalid" },
  rate_limit: { label: "Rate limited", hint: "Provider quota exceeded — try again later" },
  timeout: { label: "Timed out", hint: "The operation took too long" },
  parse_error: { label: "Parse error", hint: "AI returned malformed output" },
  provider_error: { label: "Provider error", hint: "The AI provider returned an error" },
  file_error: { label: "File error", hint: "The input file could not be read" },
  validation: { label: "Needs review", hint: "Extraction succeeded but needs human review" },
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
