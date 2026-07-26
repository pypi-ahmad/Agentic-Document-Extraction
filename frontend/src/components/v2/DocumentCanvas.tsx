"use client";

import { FileSearch, LoaderCircle, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

export interface DocumentSource {
  url: string;
  mimeType: string;
  label: string;
  remote: boolean;
}

export function DocumentCanvas({
  source,
  status,
  errorMessage,
}: {
  source: DocumentSource | null;
  status: string | null;
  errorMessage: string | null;
}) {
  const previewable = !source || source.mimeType.startsWith("image/") || source.mimeType === "application/pdf";
  const [previewUrl, setPreviewUrl] = useState(source?.remote ? null : source?.url ?? null);
  const [previewState, setPreviewState] = useState<"idle" | "loading" | "ready" | "error">(
    source?.remote ? "loading" : source ? "ready" : "idle",
  );

  useEffect(() => {
    if (!source || !previewable) {
      setPreviewUrl(null);
      setPreviewState(source ? "error" : "idle");
      return;
    }
    if (!source.remote) {
      setPreviewUrl(source.url);
      setPreviewState("ready");
      return;
    }

    const controller = new AbortController();
    let objectUrl: string | null = null;
    setPreviewUrl(null);
    setPreviewState("loading");
    void fetch(source.url, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Document preview unavailable");
        objectUrl = URL.createObjectURL(await response.blob());
        if (!controller.signal.aborted) {
          setPreviewUrl(objectUrl);
          setPreviewState("ready");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setPreviewState("error");
      });

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [previewable, source]);

  return (
    <section className="document-canvas" aria-label="Document viewer">
      <div className="document-toolbar">
        <div>
          <FileSearch size={15} />
          <span>{source?.label ?? "Document preview"}</span>
        </div>
        {status && <span className={`canvas-status ${status}`}>{status.replaceAll("_", " ")}</span>}
      </div>
      <div className="document-stage">
        {previewState === "loading" && (
          <div className="canvas-message"><LoaderCircle className="spin" size={23} /><span>Loading document preview…</span></div>
        )}
        {previewState === "error" && (
          <div className="canvas-message"><TriangleAlert size={23} /><strong>Preview unavailable</strong><span>Use the artifact download from Results.</span></div>
        )}
        {previewState === "idle" && (
          <div className="canvas-message">
            <FileSearch size={27} />
            <strong>{status === "failed" ? "Extraction failed" : "Choose a document to begin"}</strong>
            <span>{errorMessage ?? (status ? "A verified document preview will appear when available." : "PDF, PNG, JPEG, WebP, or TIFF")}</span>
          </div>
        )}
        {previewState === "ready" && previewUrl && source?.mimeType.startsWith("image/") && (
          // Runtime object URLs cannot use the static Next image optimizer.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={previewUrl} alt={`${source.label} preview`} />
        )}
        {previewState === "ready" && previewUrl && !source?.mimeType.startsWith("image/") && (
          <iframe title={`${source?.label} document preview`} src={previewUrl} sandbox="" />
        )}
      </div>
    </section>
  );
}
