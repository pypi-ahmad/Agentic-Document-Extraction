import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";
import type { AgenticParseJob } from "@/lib/api";

const api = vi.hoisted(() => ({
  cancelParseJob: vi.fn(),
  createParseJob: vi.fn(),
  getParseJob: vi.fn(),
  getParseTrace: vi.fn(),
  listParseReviews: vi.fn(),
  listExtractionSchemas: vi.fn(),
  listParseJobs: vi.fn(),
}));

const createObjectURL = vi.fn();
const revokeObjectURL = vi.fn();
const fetchMock = vi.fn();

Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });

vi.mock("@/lib/api", () => ({
  apiResourceUrl: (path: string) => path,
  artifactUrl: ({ download_url }: { download_url: string }) => download_url,
  cancelParseJob: api.cancelParseJob,
  createParseJob: api.createParseJob,
  getParseJob: api.getParseJob,
  getParseTrace: api.getParseTrace,
  listParseReviews: api.listParseReviews,
  listExtractionSchemas: api.listExtractionSchemas,
  listParseJobs: api.listParseJobs,
}));

function job(overrides: Partial<AgenticParseJob> = {}): AgenticParseJob {
  return {
    id: "job-1",
    original_filename: "invoice.pdf",
    source_mime: "application/pdf",
    source_size: 2048,
    source_sha256: "abc",
    page_count: 2,
    status: "completed",
    settings: { model: "paperplane-ade-latest" },
    models: { parser: "gpt-5.6-luna", critic: "gpt-5.6-terra" },
    completed_pages: 2,
    failed_pages: 0,
    error_code: null,
    error_message: null,
    usage: { input_tokens: 1200, cached_input_tokens: 800, output_tokens: 250, estimated_cost_usd: 0.04 },
    artifacts: [
      { id: "md", type: "markdown", mime_type: "text/markdown", size: 900, sha256: "md", download_url: "/api/v2/parse/jobs/job-1/artifacts/md", preview_url: null },
      { id: "json", type: "json", mime_type: "application/json", size: 1200, sha256: "json", download_url: "/api/v2/parse/jobs/job-1/artifacts/json", preview_url: null },
      { id: "pdf", type: "annotated_pdf", mime_type: "application/pdf", size: 3000, sha256: "pdf", download_url: "/api/v2/parse/jobs/job-1/artifacts/pdf", preview_url: "/api/v2/parse/jobs/job-1/artifacts/pdf?disposition=inline" },
    ],
    source_preview_url: "/api/v2/parse/jobs/job-1/source",
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
  api.listParseJobs.mockResolvedValue([]);
  api.listParseReviews.mockResolvedValue([]);
  api.getParseTrace.mockResolvedValue([]);
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

  it("shows only the OpenAI Parse pipeline and its three ADE model aliases", async () => {
    render(<HomePage />);

    expect(await screen.findByText("Grounded document extraction")).toBeInTheDocument();
    expect(screen.getByText("gpt-5.6-luna")).toBeInTheDocument();
    expect(screen.getByText("gpt-5.6-terra")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Fast/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Balanced/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Audit/ })).toBeInTheDocument();
    expect(screen.queryByText(/PaddleOCR|Ollama/i)).not.toBeInTheDocument();
  });

  it("stages a file and submits the selected Parse model", async () => {
    api.createParseJob.mockResolvedValue(job({ status: "queued", completed_pages: 0 }));
    render(<HomePage />);
    const file = new File(["pdf"], "invoice.pdf", { type: "application/pdf" });

    fireEvent.change(screen.getByLabelText("Choose document"), { target: { files: [file] } });

    expect(createObjectURL).toHaveBeenCalledWith(file);
    expect(screen.getByTitle("invoice.pdf document preview")).toHaveAttribute("src", "blob:paperplane-preview");
    expect(screen.getByTitle("invoice.pdf document preview")).toHaveAttribute("sandbox", "");

    fireEvent.change(screen.getByLabelText("Processing model"), { target: { value: "paperplane-ade-audit-latest" } });
    fireEvent.click(screen.getByRole("button", { name: "Start parsing" }));

    await waitFor(() => expect(api.createParseJob).toHaveBeenCalledWith(file, {
      model: "paperplane-ade-audit-latest",
    }));
    expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
  });

  it("renders core metrics and inline annotated PDF actions for a completed job", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/source")) {
        return new Response(new Blob(["pdf"], { type: "application/pdf" }), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    api.listParseJobs.mockResolvedValue([job()]);
    render(<HomePage />);

    expect(await screen.findByText("2/2")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("67% cache hit")).not.toBeInTheDocument();
    expect(screen.queryByText("Prompt input reuse")).not.toBeInTheDocument();
    expect(screen.queryByText("$0.0400")).not.toBeInTheDocument();
    expect(screen.queryByText("Estimated cost")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Markdown" })).toHaveAttribute("href", "/api/v2/parse/jobs/job-1/artifacts/md");
    expect(screen.getByRole("link", { name: "Download Annotated PDF" })).toHaveAttribute("href", "/api/v2/parse/jobs/job-1/artifacts/pdf");
    expect(screen.getByTitle("Annotated PDF preview")).toHaveAttribute("src", "/api/v2/parse/jobs/job-1/artifacts/pdf?disposition=inline");
    expect(screen.getByTitle("Annotated PDF preview")).toHaveAttribute("sandbox", "");
    expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByTitle("invoice.pdf document preview")).toHaveAttribute("src", "blob:paperplane-preview");
  });

  it("clears staged input when starting a new extraction", () => {
    render(<HomePage />);
    const file = new File(["pdf"], "stale.pdf", { type: "application/pdf" });

    fireEvent.change(screen.getByLabelText("Choose document"), { target: { files: [file] } });
    expect(screen.getByRole("button", { name: "Start parsing" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "New extraction" }));

    expect(screen.getByRole("button", { name: "Start parsing" })).toBeDisabled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:paperplane-preview");
  });

  it("previews formatted grounded JSON", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/source")) {
        return new Response(new Blob(["pdf"], { type: "application/pdf" }), { status: 200 });
      }
      if (String(input).endsWith("/json")) {
        return new Response('{"answer":42}', { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    api.listParseJobs.mockResolvedValue([job()]);
    render(<HomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "JSON" }));

    expect(await screen.findByText(/"answer": 42/)).toBeInTheDocument();
  });

  it("keeps artifact downloads available when preview loading fails", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/source")) {
        return new Response(new Blob(["pdf"], { type: "application/pdf" }), { status: 200 });
      }
      return new Response("unavailable", { status: 503 });
    });
    api.listParseJobs.mockResolvedValue([job()]);
    render(<HomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Markdown" }));

    expect(await screen.findByText("Preview unavailable. Download the artifact to inspect it.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download Markdown" })).toHaveAttribute("href", "/api/v2/parse/jobs/job-1/artifacts/md");
  });

  it("cancels an active job", async () => {
    const running = job({ status: "processing", completed_pages: 1 });
    api.listParseJobs.mockResolvedValue([running]);
    api.cancelParseJob.mockResolvedValue({ ...running, status: "cancelling" });
    render(<HomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Stop parsing" }));

    await waitFor(() => expect(api.cancelParseJob).toHaveBeenCalledWith("job-1"));
    expect(screen.getByText("Cancelling")).toBeInTheDocument();
  });

  it("previews the original source and exposes the agentic result tabs", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/source")) {
        return new Response(new Blob(["pdf"], { type: "application/pdf" }), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    });
    api.listParseJobs.mockResolvedValue([job()]);
    render(<HomePage />);

    expect(await screen.findByTitle("invoice.pdf document preview")).toHaveAttribute("src", "blob:paperplane-preview");
    expect(screen.getByRole("button", { name: "Annotated PDF" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Extract" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Agent Trace" })).toBeInTheDocument();
  });

  it("renders structured agent trace events without chain-of-thought", async () => {
    api.listParseJobs.mockResolvedValue([job()]);
    api.getParseTrace.mockResolvedValue([{ agent: "page-supervisor", action: "dispatch", summary: "Sent page 1 to table and text specialists.", page_number: 1 }]);
    render(<HomePage />);

    await waitFor(() => expect(api.getParseTrace).toHaveBeenCalledWith("job-1", expect.any(AbortSignal)));
    fireEvent.click(await screen.findByRole("button", { name: "Agent Trace" }));

    expect(await screen.findByText("Sent page 1 to table and text specialists.")).toBeInTheDocument();
    expect(screen.queryByText(/chain.of.thought/i)).not.toBeInTheDocument();
  });
});
