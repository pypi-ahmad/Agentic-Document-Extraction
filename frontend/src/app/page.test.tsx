import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";
import type { OllamaModel, ParseJob } from "@/lib/api";

const api = vi.hoisted(() => ({
  cancelJob: vi.fn(),
  createEvaluationRun: vi.fn(),
  createJob: vi.fn(),
  createParseBatch: vi.fn(),
  evaluateJob: vi.fn(),
  getEvaluationRun: vi.fn(),
  getJob: vi.fn(),
  getMarkdown: vi.fn(),
  getRuntimeCapabilities: vi.fn(),
  listJobs: vi.fn(),
  listParseBatches: vi.fn(),
  listEvaluationRuns: vi.fn(),
  listExtractionSchemas: vi.fn(),
  listOllamaModels: vi.fn(),
  listSubdocuments: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  apiResourceUrl: (path: string) => path,
  artifactUrl: ({ download_url }: { download_url: string }) => download_url,
  cancelJob: api.cancelJob,
  createEvaluationRun: api.createEvaluationRun,
  createJob: api.createJob,
  createParseBatch: api.createParseBatch,
  evaluateJob: api.evaluateJob,
  getEvaluationRun: api.getEvaluationRun,
  getJob: api.getJob,
  getMarkdown: api.getMarkdown,
  getRuntimeCapabilities: api.getRuntimeCapabilities,
  listJobs: api.listJobs,
  listParseBatches: api.listParseBatches,
  listEvaluationRuns: api.listEvaluationRuns,
  listExtractionSchemas: api.listExtractionSchemas,
  listOllamaModels: api.listOllamaModels,
  listSubdocuments: api.listSubdocuments,
}));

vi.mock("@/components/ArtifactGallery", () => ({ ArtifactGallery: () => null }));
vi.mock("@/components/QualityDiagnostics", () => ({ QualityDiagnostics: () => null }));
vi.mock("@/components/SchemaWorkspace", () => ({ SchemaWorkspace: () => null }));
vi.mock("@/components/ReviewWorkspace", () => ({ ReviewWorkspace: () => null }));
vi.mock("@/components/DocumentInspector", () => ({ DocumentInspector: () => <div data-testid="document-inspector" /> }));

const compatible: OllamaModel = {
  name: "qwen3.5:9b",
  digest: "qwen",
  size: 1,
  modified_at: null,
  capabilities: ["completion", "vision"],
  compatible: true,
  inspection_error: null,
};
const incompatible: OllamaModel = {
  ...compatible,
  name: "ornith:latest",
  digest: "ornith",
  capabilities: ["completion"],
  compatible: false,
};

function job(filename = "existing.pdf", overrides: Partial<ParseJob> = {}): ParseJob {
  return {
    id: "job-1",
    original_filename: filename,
    source_size: 1024,
    page_count: 1,
    status: "completed",
    settings: {
      segment_documents: true,
      document_profile: "auto",
      structured_extraction: true,
      allow_sensitive_cloud: false,
      processing_mode: "local_only",
      quality_overrides: {},
      ocr_provider: "ollama",
      ocr_model: compatible.name,
      review_provider: "ollama",
      review_model: compatible.name,
      extraction_schema_id: null,
      extraction_provider: "ollama",
      extraction_model: compatible.name,
      cloud_mode: "off",
      blind_local_retry: false,
      start_page: 1,
      end_page: null,
      input_mode: "mixed",
      dpi: 200,
      marginalia_policy: "remove_repeated",
      describe_figures: true,
      grounding_pdf: true,
      searchable_pdf: true,
      bundle: true,
    },
    current_page: null,
    current_batch: null,
    total_batches: 1,
    detected_profile: "general_scanned",
    profile_confidence: 0.5,
    segmentation_status: "completed",
    subdocument_count: 0,
    is_partial: false,
    completed_pages: 1,
    failed_pages: 0,
    warning_count: 0,
    review_required_count: 0,
    quality_policy: null,
    error_message: null,
    model_name: compatible.name,
    model_digest: compatible.digest,
    review_model_name: compatible.name,
    review_model_digest: compatible.digest,
    extraction_schema: null,
    extraction_model_name: null,
    extraction_model_digest: null,
    source_preview_url: "/api/parse-jobs/job-1/source",
    output_revision: 0,
    verified_export_ready: true,
    batch_id: null,
    batch_ordinal: null,
    created_at: "2026-07-24T12:00:00Z",
    started_at: "2026-07-24T12:00:00Z",
    completed_at: "2026-07-24T12:00:01Z",
    pages: [],
    artifacts: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  window.localStorage.clear();
  document.documentElement.dataset.theme = "dark";
    api.listJobs.mockResolvedValue([]);
    api.listParseBatches.mockResolvedValue([]);
  api.listEvaluationRuns.mockResolvedValue([]);
  api.listExtractionSchemas.mockResolvedValue([]);
  api.listOllamaModels.mockResolvedValue([compatible, incompatible]);
  api.listSubdocuments.mockResolvedValue([]);
  api.getMarkdown.mockResolvedValue("");
  api.getRuntimeCapabilities.mockResolvedValue({
    paddleocr_vl_available: true,
    parser_model: "PaddleOCR-VL-1.6",
    pipeline_version: "v1.6",
    paddleocr_vl: {
      available: true,
      docker_available: true,
      gpu_available: true,
      image_present: true,
      cache_ready: true,
      image: "paddleocr-vl@test",
      error: null,
      pull_command: null,
    },
    providers: [],
  });
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:document") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
});

afterEach(() => cleanup());

describe("HomePage", () => {
  it("shows discovered models and ignores corrupt saved selections", async () => {
    window.localStorage.setItem("paperplane:model-selection:v1", "not-json");
    render(<HomePage />);

    await screen.findByText("PaddleOCR-VL-1.6 ready");
    fireEvent.click(screen.getByRole("button", { name: /Parse settings/i }));
    const ocr = await screen.findByLabelText("Local OCR model");
    expect(ocr).toHaveValue(compatible.name);
    expect(screen.queryByRole("option", { name: /ornith:latest/ })).not.toBeInTheDocument();
    expect(screen.getByText("PaddleOCR-VL-1.6 ready")).toBeInTheDocument();
    expect(window.localStorage.getItem("paperplane:model-selection:v1")).toContain(compatible.name);
  });

  it("does not show Stop for a completed parse", async () => {
    api.listJobs.mockResolvedValue([job()]);
    render(<HomePage />);

    await screen.findAllByText("existing.pdf");
    expect(screen.queryByRole("button", { name: "Stop parsing" })).not.toBeInTheDocument();
  });

  it("stages a selected document before parsing", async () => {
    render(<HomePage />);
    await screen.findByText("PaddleOCR-VL-1.6 ready");
    const file = new File(["pdf"], "invoice.pdf", { type: "application/pdf" });
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input!, { target: { files: [file] } });

    expect(await screen.findByText("invoice.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parse document" })).toBeEnabled();
    expect(api.createJob).not.toHaveBeenCalled();
  });

  it("disables parsing when PaddleOCR-VL is unavailable", async () => {
    api.getRuntimeCapabilities.mockResolvedValue({
      paddleocr_vl_available: false,
      parser_model: "PaddleOCR-VL-1.6",
      pipeline_version: "v1.6",
      paddleocr_vl: {
        available: false,
        docker_available: true,
        gpu_available: true,
        image_present: false,
        cache_ready: true,
        image: "paddleocr-vl@test",
        error: "PaddleOCR-VL image is not installed",
        pull_command: "docker pull paddleocr-vl@test",
      },
      providers: [],
    });
    render(<HomePage />);
    const file = new File(["pdf"], "invoice.pdf", { type: "application/pdf" });
    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
      target: { files: [file] },
    });

    expect(await screen.findByText("PaddleOCR-VL unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parse document" })).toBeDisabled();
  });

  it("keeps a dropped document after a failed submission and retries it", async () => {
    api.listJobs.mockResolvedValue([job()]);
    api.createJob.mockRejectedValueOnce(new Error("Backend restarted"));
    api.createJob.mockResolvedValueOnce(job("new.pdf"));
    render(<HomePage />);
    await screen.findAllByText("existing.pdf");
    await screen.findByText("PaddleOCR-VL-1.6 ready");
    const file = new File(["pdf"], "new.pdf", { type: "application/pdf" });

    fireEvent.drop(screen.getByRole("main"), {
      dataTransfer: { files: [file], types: ["Files"] },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Parse document" }));

    expect(await screen.findByText("Backend restarted")).toBeInTheDocument();
    expect(screen.getByText("new.pdf")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Parse document" }));
    await waitFor(() => expect(api.createJob).toHaveBeenCalledTimes(2));
  });

  it("can parse without Ollama and exposes theme and setting help", async () => {
    api.listOllamaModels.mockRejectedValue(new Error("Paperplane backend is unavailable."));
    render(<HomePage />);
    await screen.findByText("PaddleOCR-VL-1.6 ready");
    const file = new File(["image"], "scan.png", { type: "image/png" });

    fireEvent.drop(screen.getByRole("main"), {
      dataTransfer: { files: [file], types: ["Files"] },
    });
    expect(await screen.findByText("scan.png")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parse document" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Use light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("paperplane:theme:v1")).toBe("light");

    fireEvent.click(screen.getByRole("button", { name: /Parse settings/i }));
    expect(screen.getByText(/backend is unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "About Marginalia" })).toHaveAttribute("aria-describedby");
    expect(screen.getByRole("tooltip", { name: /Remove repeated omits page numbers/i })).toBeInTheDocument();
  });

  it("keeps local OCR separate from adaptive cloud context", async () => {
    api.getRuntimeCapabilities.mockResolvedValue({
      paddleocr_vl_available: true,
      parser_model: "PaddleOCR-VL-1.6",
      pipeline_version: "v1.6",
      paddleocr_vl: {
        available: true,
        docker_available: true,
        gpu_available: true,
        image_present: true,
        cache_ready: true,
        image: "paddleocr-vl@test",
        error: null,
        pull_command: null,
      },
      providers: [
        {
          id: "openai",
          name: "OpenAI",
          state: "ready",
          models: [{ id: "vision-model", name: "Vision model" }],
        },
      ],
    });
    render(<HomePage />);

    await screen.findByText("PaddleOCR-VL-1.6 ready");
    fireEvent.click(screen.getByRole("button", { name: /Parse settings/i }));
    expect(screen.getByLabelText("Local OCR model")).toHaveValue(compatible.name);

    fireEvent.change(screen.getByLabelText("Processing mode"), {
      target: { value: "hybrid" },
    });

    expect(screen.getByLabelText("Processing mode")).toHaveValue("hybrid");
    expect(screen.getByLabelText("Cloud context provider")).toHaveValue("openai");
    expect(screen.getByLabelText("Cloud context model")).toHaveValue("vision-model");
    expect(screen.getByLabelText("Blind local retry on cloud disagreement")).not.toBeChecked();
    fireEvent.click(screen.getByLabelText("Blind local retry on cloud disagreement"));
    expect(screen.getByLabelText("Blind local retry on cloud disagreement")).toBeChecked();
    expect(screen.getByText("Cloud context enabled")).toBeInTheDocument();
  });

  it("stops an active parse and shows its cancelling state", async () => {
    const running = job("running.pdf", {
      status: "processing",
      completed_pages: 0,
      completed_at: null,
    });
    api.listJobs.mockResolvedValue([running]);
    api.cancelJob.mockResolvedValue({ ...running, status: "cancelling" });
    render(<HomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Stop parsing" }));

    await waitFor(() => expect(api.cancelJob).toHaveBeenCalledWith("job-1"));
    expect(screen.getByRole("button", { name: "Stopping parse" })).toBeDisabled();
    expect(screen.getByText("Cancelling")).toBeInTheDocument();
  });

  it("opens evaluation mode for completed jobs and dataset benchmarks", async () => {
    api.listJobs.mockResolvedValue([job()]);
    render(<HomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Evaluate" }));

    expect(await screen.findByText("Evaluate a completed parse")).toBeInTheDocument();
    expect(screen.getByLabelText("Completed job")).toHaveTextContent("existing.pdf");
    expect(screen.getByText("Parse and evaluate a batch")).toBeInTheDocument();
    expect(api.listEvaluationRuns).toHaveBeenCalled();
  });

  it("re-enables Stop when cancellation fails", async () => {
    const running = job("running.pdf", {
      status: "processing",
      completed_pages: 0,
      completed_at: null,
    });
    api.listJobs.mockResolvedValue([running]);
    api.cancelJob.mockRejectedValue(new Error("Could not stop job"));
    render(<HomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Stop parsing" }));

    expect(await screen.findByText("Could not stop job")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop parsing" })).toBeEnabled();
  });
});
