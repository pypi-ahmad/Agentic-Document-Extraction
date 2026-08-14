const API_BASE = "/api";
const BACKEND_UNAVAILABLE_MESSAGE =
  "Paperplane backend is unavailable. Start FastAPI and confirm the frontend backend URL and port.";

class ApiError extends Error {
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
    throw new ApiError(0, BACKEND_UNAVAILABLE_MESSAGE);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail?.message === "string"
          ? detail.message
          : response.status >= 500
            ? BACKEND_UNAVAILABLE_MESSAGE
            : `Request failed (${response.status})`;
    throw new ApiError(response.status, message);
  }
  return response.json();
}

export type ParseModel =
  | "paperplane-ade-fast-latest"
  | "paperplane-ade-latest"
  | "paperplane-ade-audit-latest";

export interface ParseNode {
  id: string;
  type: string;
  page: number | null;
  children: ParseNode[];
}

export interface ParseResponse {
  markdown: string;
  metadata: {
    job_id: string;
    model: string;
    page_count: number;
    output_characters: number;
    failed_pages: number[];
    duration_ms: number | null;
  };
  structure: ParseNode;
}

export async function parseDocument(file: File, model: ParseModel): Promise<ParseResponse> {
  const body = new FormData();
  body.append("file", file);
  body.append("model", model);
  return request<ParseResponse>("/v2/parse", { method: "POST", body });
}
