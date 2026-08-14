import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";
import { parseDocument, type ParseResponse } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, parseDocument: vi.fn() };
});

vi.mock("@/components/v2/DocumentCanvas", () => ({
  DocumentCanvas: ({ status }: { status: string | null }) => (
    <div aria-label="Document viewer">{status ?? "idle"}</div>
  ),
}));

const result: ParseResponse = {
  markdown: "<!-- page_number=1 -->\n\nInvoice total: 42",
  metadata: {
    job_id: "request-1",
    model: "paperplane-ade-latest",
    page_count: 1,
    output_characters: 47,
    failed_pages: [],
    duration_ms: 125,
  },
  structure: {
    id: "document-1",
    type: "document",
    page: null,
    children: [
      {
        id: "page-1",
        type: "page",
        page: 1,
        children: [{ id: "text-1", type: "text", page: 1, children: [] }],
      },
    ],
  },
};

describe("stateless document workspace", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.mocked(parseDocument).mockReset();
    vi.mocked(parseDocument).mockResolvedValue(result);
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:preview"),
      revokeObjectURL: vi.fn(),
    });
  });

  it("opens as a simple parse workspace", () => {
    render(<HomePage />);

    expect(screen.getByText("Stateless document extraction")).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Parse document" }).disabled).toBe(true);
    expect(screen.queryByText("Runs")).toBeNull();
  });

  it("sends the selected file directly to Parse", async () => {
    render(<HomePage />);
    const file = new File(["document"], "invoice.pdf", { type: "application/pdf" });

    fireEvent.change(screen.getByLabelText("Choose document"), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText("Processing model"), {
      target: { value: "paperplane-ade-audit-latest" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Parse document" }));

    await waitFor(() =>
      expect(parseDocument).toHaveBeenCalledWith(file, "paperplane-ade-audit-latest"),
    );
    expect(await screen.findByText("Invoice total: 42", { exact: false })).toBeTruthy();
  });

  it("switches between Markdown and JSON output", async () => {
    render(<HomePage />);
    const file = new File(["document"], "invoice.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Choose document"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Parse document" }));

    await screen.findByText("Invoice total: 42", { exact: false });
    fireEvent.click(screen.getByRole("button", { name: "JSON" }));

    expect(screen.getByText('"job_id": "request-1"', { exact: false })).toBeTruthy();
  });

  it("clears the current document for a new extraction", async () => {
    render(<HomePage />);
    const file = new File(["document"], "invoice.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Choose document"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Parse document" }));
    await screen.findByText("Invoice total: 42", { exact: false });

    fireEvent.click(screen.getByRole("button", { name: "New extraction" }));

    expect(screen.getByText("Choose a document")).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Parse document" }).disabled).toBe(true);
  });
});
