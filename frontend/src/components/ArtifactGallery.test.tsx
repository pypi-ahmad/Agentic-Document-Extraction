import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ArtifactGallery } from "./ArtifactGallery";
import type { Artifact } from "../lib/api";

const artifacts: Artifact[] = [
  {
    id: "bundle",
    type: "bundle",
    filename: "document-bundle.zip",
    mime_type: "application/zip",
    size: 2048,
    sha256: "a".repeat(64),
    region_id: null,
    download_url: "/api/parse-jobs/job/artifacts/bundle",
    preview_url: null,
  },
  {
    id: "context",
    type: "context_json",
    filename: "document.context.json",
    mime_type: "application/json",
    size: 42,
    sha256: "b".repeat(64),
    region_id: null,
    download_url: "/api/parse-jobs/job/artifacts/context_json",
    preview_url: "/api/parse-jobs/job/artifacts/context_json?disposition=inline",
  },
  {
    id: "annotated",
    type: "grounding_pdf",
    filename: "annotated.pdf",
    mime_type: "application/pdf",
    size: 4096,
    sha256: "c".repeat(64),
    region_id: null,
    download_url: "/api/parse-jobs/job/artifacts/grounding_pdf",
    preview_url: "/api/parse-jobs/job/artifacts/grounding_pdf?disposition=inline",
  },
];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ArtifactGallery", () => {
  it("selects the annotated PDF first and exposes every download", () => {
    render(<ArtifactGallery jobId="job" artifacts={artifacts} />);

    expect(screen.getByTitle("Annotated PDF preview")).toBeInTheDocument();
    expect(screen.getAllByTitle(/Download/i)).toHaveLength(3);
    expect(screen.getByRole("button", { name: /document-bundle.zip/i })).toBeInTheDocument();
  });

  it("pretty prints JSON and explains that ZIP is download only", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('{"chunks":[1]}', { status: 200 }),
    );
    render(<ArtifactGallery jobId="job" artifacts={artifacts} />);

    fireEvent.click(screen.getByRole("button", { name: /document.context.json/i }));
    await waitFor(() => expect(screen.getByText(/"chunks": \[/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /document-bundle.zip/i }));
    expect(screen.getByText(/download-only/i)).toBeInTheDocument();
  });
});
