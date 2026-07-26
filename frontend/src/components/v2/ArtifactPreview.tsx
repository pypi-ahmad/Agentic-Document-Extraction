"use client";

import { Download, FileArchive, FileCode2, FileText, LoaderCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { artifactUrl, type V2Artifact } from "@/lib/api";

const NAMES: Record<string, string> = {
  markdown: "Markdown",
  clean_markdown: "Markdown",
  document_json: "Grounded JSON",
  extraction_json: "Schema extraction",
  annotated_pdf: "Annotated PDF",
  usage_json: "Usage report",
  usage: "Usage report",
};

function name(artifact: V2Artifact) {
  return NAMES[artifact.type] ?? artifact.type.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isText(artifact: V2Artifact) {
  return artifact.mime_type.startsWith("text/") || artifact.mime_type === "application/json";
}

export function ArtifactPreview({ jobId, artifacts }: { jobId: string; artifacts: V2Artifact[] }) {
  const defaultId = useMemo(
    () => artifacts.find((artifact) => isText(artifact))?.id ?? artifacts[0]?.id ?? null,
    [artifacts],
  );
  const [selectedId, setSelectedId] = useState<string | null>(defaultId);
  const [content, setContent] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");

  useEffect(() => setSelectedId(defaultId), [defaultId, jobId]);

  const selected = artifacts.find((artifact) => artifact.id === selectedId) ?? null;

  useEffect(() => {
    setContent("");
    if (!selected || !isText(selected)) {
      setState("idle");
      return;
    }

    const controller = new AbortController();
    setState("loading");
    void fetch(artifactUrl(selected), { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Preview unavailable");
        const value = await response.text();
        if (selected.mime_type !== "application/json") return value;
        try {
          return JSON.stringify(JSON.parse(value), null, 2);
        } catch {
          return value;
        }
      })
      .then((value) => {
        if (!controller.signal.aborted) {
          setContent(value);
          setState("ready");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setState("error");
      });
    return () => controller.abort();
  }, [selected]);

  if (!artifacts.length) {
    return <div className="artifact-preview-empty"><FileArchive size={25} /><span>Grounded outputs appear when extraction completes.</span></div>;
  }

  return (
    <div className="artifact-workspace">
      <div className="artifact-tabs" aria-label="Generated artifacts">
        {artifacts.map((artifact) => (
          <div className={selected?.id === artifact.id ? "selected" : ""} key={artifact.id}>
            <button type="button" aria-label={`Preview ${name(artifact)}`} aria-pressed={selected?.id === artifact.id} onClick={() => setSelectedId(artifact.id)}>
              {artifact.mime_type === "application/json" ? <FileCode2 size={14} /> : <FileText size={14} />}
              {name(artifact)}
            </button>
            <a href={artifactUrl(artifact)} download aria-label={`Download ${name(artifact)}`} title={`Download ${name(artifact)}`}><Download size={14} /></a>
          </div>
        ))}
      </div>
      <div className="artifact-content" aria-live="polite">
        {state === "loading" && <div className="artifact-message"><LoaderCircle className="spin" size={20} /> Loading preview…</div>}
        {state === "ready" && <pre>{content}</pre>}
        {state === "error" && <div className="artifact-message">Preview unavailable. Download the artifact to inspect it.</div>}
        {state === "idle" && selected && !isText(selected) && <div className="artifact-message"><FileArchive size={24} />This artifact is download-only.</div>}
      </div>
    </div>
  );
}
