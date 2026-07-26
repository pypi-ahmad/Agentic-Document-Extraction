import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";
import type { V2Job } from "@/lib/api";

const api = vi.hoisted(() => ({
  cancelV2Job: vi.fn(),
  createV2Job: vi.fn(),
  evaluateV2Job: vi.fn(),
  getV2Job: vi.fn(),
  listExtractionSchemas: vi.fn(),
  listV2Jobs: vi.fn(),
}));

const createObjectURL = vi.fn();
const revokeObjectURL = vi.fn();
const fetchMock = vi.fn();

Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });

vi.mock("@/lib/api", () => ({
  artifactUrl: ({ download_url }: { download_url: string }) => download_url,
  cancelV2Job: api.cancelV2Job,
  createV2Job: api.createV2Job,
  evaluateV2Job: api.evaluateV2Job,
  getV2Job: api.getV2Job,
  listExtractionSchemas: api.listExtractionSchemas,
  listV2Jobs: api.listV2Jobs,
}));

function job(overrides: Partial<V2Job> = {}): V2Job {
  return {
    id: "job-1",
    original_filename: "invoice.pdf",
    source_mime: "application/pdf",
    source_size: 2048,
    source_sha256: "abc",
    page_count: 2,
    status: "completed",
    settings: { mode: "balanced", segment_documents: true, extraction_schema_id: null },
    models: { draft: "gpt-5.6-luna", verification: "gpt-5.6-terra" },
    completed_pages: 2,
    failed_pages: 0,
    error_code: null,
    error_message: null,
    usage: { input_tokens: 1200, cached_input_tokens: 800, output_tokens: 250, estimated_cost_usd: 0.04 },
    artifacts: [
      { id: "md", type: "markdown", mime_type: "text/markdown", size: 900, sha256: "md", download_url: "/api/v2/jobs/job-1/artifacts/md" },
      { id: "json", type: "document_json", mime_type: "application/json", size: 1200, sha256: "json", download_url: "/api/v2/jobs/job-1/artifacts/json" },
      { id: "pdf", type: "annotated_pdf", mime_type: "application/pdf", size: 3000, sha256: "pdf", download_url: "/api/v2/jobs/job-1/artifacts/pdf" },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  fetchMock.mockResolvedValue(new Response("not found", { status: 404 }));
  createObjectURL.mockReturnValue("blob:paperplane-preview");
  vi.stubGlobal("fetch", fetchMock);
  document.documentElement.dataset.theme = "dark";
  localStorage.clear();
  api.listV2Jobs.mockResolvedValue([]);
  api.listExtractionSchemas.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("OpenAI document workspace", () => {
  it("opens as an Evidence Studio configuration workspace", async () => {
    render(<HomePage />);

    expect(await screen.findByRole("navigation", { name: "Extraction runs" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Configure" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Evaluate" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText("No extraction runs yet")).toBeInTheDocument();
  });

  it("switches themes and persists the explicit preference", () => {
    render(<HomePage />);

    fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));

    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(localStorage.getItem("paperplane:theme:v1")).toBe("light");

    fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(localStorage.getItem("paperplane:theme:v1")).toBe("dark");
  });

  it("still switches theme when preference storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(() => {
      throw new DOMException("Storage unavailable");
    });
    render(<HomePage />);

    fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));

    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
  });

  it("shows only the OpenAI V2 pipeline and its three processing modes", async () => {
    render(<HomePage />);

    expect(await screen.findByText("Grounded document extraction")).toBeInTheDocument();
    expect(screen.getByText("gpt-5.6-luna")).toBeInTheDocument();
    expect(screen.getByText("gpt-5.6-terra")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Economy/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Balanced/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Audit/ })).toBeInTheDocument();
    expect(screen.queryByText(/PaddleOCR|Ollama/i)).not.toBeInTheDocument();
  });

  it("stages a file and submits V2 settings", async () => {
    api.createV2Job.mockResolvedValue(job({ status: "queued", completed_pages: 0 }));
    render(<HomePage />);
    const file = new File(["pdf"], "invoice.pdf", { type: "application/pdf" });

    fireEvent.change(screen.getByLabelText("Choose document"), { target: { files: [file] } });

    expect(createObjectURL).toHaveBeenCalledWith(file);
    expect(screen.getByTitle("invoice.pdf document preview")).toHaveAttribute("src", "blob:paperplane-preview");
    expect(screen.getByTitle("invoice.pdf document preview")).toHaveAttribute("sandbox", "");

    fireEvent.change(screen.getByLabelText("Processing mode"), { target: { value: "audit" } });
    fireEvent.click(screen.getByRole("button", { name: "Start extraction" }));

    await waitFor(() => expect(api.createV2Job).toHaveBeenCalledWith(file, {
      mode: "audit",
      segment_documents: true,
      extraction_schema_id: null,
    }));
    expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
  });

  it("renders cache usage, cost, and audit artifacts for a completed job", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/pdf")) {
        return new Response(new Blob(["pdf"], { type: "application/pdf" }), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    api.listV2Jobs.mockResolvedValue([job()]);
    render(<HomePage />);

    expect(await screen.findByText("67% cache hit")).toBeInTheDocument();
    expect(screen.getByText("$0.0400")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Markdown" })).toHaveAttribute("href", "/api/v2/jobs/job-1/artifacts/md");
    expect(screen.getByRole("link", { name: "Download Annotated PDF" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByTitle("invoice.pdf document preview")).toHaveAttribute("src", "blob:paperplane-preview");
  });

  it("clears staged input when starting a new extraction", () => {
    render(<HomePage />);
    const file = new File(["pdf"], "stale.pdf", { type: "application/pdf" });

    fireEvent.change(screen.getByLabelText("Choose document"), { target: { files: [file] } });
    expect(screen.getByRole("button", { name: "Start extraction" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "New extraction" }));

    expect(screen.getByRole("button", { name: "Start extraction" })).toBeDisabled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:paperplane-preview");
  });

  it("previews formatted grounded JSON", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/pdf")) {
        return new Response(new Blob(["pdf"], { type: "application/pdf" }), { status: 200 });
      }
      if (String(input).endsWith("/json")) {
        return new Response('{"answer":42}', { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    api.listV2Jobs.mockResolvedValue([job()]);
    render(<HomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Preview Grounded JSON" }));

    expect(await screen.findByText(/"answer": 42/)).toBeInTheDocument();
  });

  it("keeps artifact downloads available when preview loading fails", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/pdf")) {
        return new Response(new Blob(["pdf"], { type: "application/pdf" }), { status: 200 });
      }
      return new Response("unavailable", { status: 503 });
    });
    api.listV2Jobs.mockResolvedValue([job()]);
    render(<HomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Preview Markdown" }));

    expect(await screen.findByText("Preview unavailable. Download the artifact to inspect it.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Markdown" })).toHaveAttribute("href", "/api/v2/jobs/job-1/artifacts/md");
  });

  it("cancels an active job", async () => {
    const running = job({ status: "processing", completed_pages: 1 });
    api.listV2Jobs.mockResolvedValue([running]);
    api.cancelV2Job.mockResolvedValue({ ...running, status: "cancelling" });
    render(<HomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Stop extraction" }));

    await waitFor(() => expect(api.cancelV2Job).toHaveBeenCalledWith("job-1"));
    expect(screen.getByText("Cancelling")).toBeInTheDocument();
  });

  it("previews annotations and evaluates grounded labels", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/pdf")) {
        return new Response(new Blob(["pdf"], { type: "application/pdf" }), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    api.listV2Jobs.mockResolvedValue([job()]);
    api.evaluateV2Job.mockResolvedValue({
      schema_version: "paperplane-evaluation/v2",
      metrics: { macro_score: 0.98, text_similarity: 0.99 },
      matched_chunks: 10,
      predicted_chunks: 10,
      labeled_chunks: 10,
      unmatched_predicted: [],
      unmatched_labels: [],
    });
    render(<HomePage />);

    expect(await screen.findByTitle("invoice.pdf document preview")).toHaveAttribute("src", "blob:paperplane-preview");
    fireEvent.click(screen.getByRole("tab", { name: "Evaluate" }));

    const labels = new File(["{}"], "labels.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("Ground-truth labels"), { target: { files: [labels] } });
    fireEvent.click(screen.getByRole("button", { name: "Run evaluation" }));

    await waitFor(() => expect(api.evaluateV2Job).toHaveBeenCalledWith("job-1", labels));
    expect(await screen.findByText("98.0% macro score")).toBeInTheDocument();
  });
});
