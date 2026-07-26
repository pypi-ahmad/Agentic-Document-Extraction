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
      { id: "pdf", type: "annotated_pdf", mime_type: "application/pdf", size: 3000, sha256: "pdf", download_url: "/api/v2/jobs/job-1/artifacts/pdf" },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  document.documentElement.dataset.theme = "dark";
  localStorage.clear();
  api.listV2Jobs.mockResolvedValue([]);
  api.listExtractionSchemas.mockResolvedValue([]);
});

afterEach(cleanup);

describe("OpenAI document workspace", () => {
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
    fireEvent.change(screen.getByLabelText("Processing mode"), { target: { value: "audit" } });
    fireEvent.click(screen.getByRole("button", { name: "Start extraction" }));

    await waitFor(() => expect(api.createV2Job).toHaveBeenCalledWith(file, {
      mode: "audit",
      segment_documents: true,
      extraction_schema_id: null,
    }));
  });

  it("renders cache usage, cost, and audit artifacts for a completed job", async () => {
    api.listV2Jobs.mockResolvedValue([job()]);
    render(<HomePage />);

    expect(await screen.findByText("67% cache hit")).toBeInTheDocument();
    expect(screen.getByText("$0.0400")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Markdown/ })).toHaveAttribute("href", "/api/v2/jobs/job-1/artifacts/md");
    expect(screen.getByRole("link", { name: /Annotated PDF/ })).toBeInTheDocument();
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

    fireEvent.click(await screen.findByRole("button", { name: "Preview annotated PDF" }));
    expect(screen.getByTitle("Annotated PDF preview")).toHaveAttribute("src", "/api/v2/jobs/job-1/artifacts/pdf");

    const labels = new File(["{}"], "labels.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("Ground-truth labels"), { target: { files: [labels] } });
    fireEvent.click(screen.getByRole("button", { name: "Run evaluation" }));

    await waitFor(() => expect(api.evaluateV2Job).toHaveBeenCalledWith("job-1", labels));
    expect(await screen.findByText("98.0% macro score")).toBeInTheDocument();
  });
});
