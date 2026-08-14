"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, Eye, FileArchive, FileCode2, FileImage, FileText, Loader2 } from "lucide-react";

import { apiResourceUrl, artifactUrl, type Artifact } from "../lib/api";

const LABELS: Record<string, string> = {
  source_document: "Split source PDF",
  grounding_pdf: "Annotated PDF",
  clean_markdown: "Clean Markdown",
  llm_markdown: "LLM-ready Markdown",
  grounded_markdown: "Grounded Markdown",
  searchable_pdf: "Searchable PDF",
  context_json: "Context JSON",
  structured_blocks: "Structured blocks & citations",
  subdocument_manifest: "Sub-document manifest",
  diagnostics: "Diagnostics",
  settings: "Parse settings",
  warnings: "Warnings",
  figure: "Figure crop",
  bundle: "Complete ZIP bundle",
  schema_extraction: "Schema-shaped extraction",
  schema_table: "Grounded table rows",
};

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function ArtifactIcon({ artifact }: { artifact: Artifact }) {
  if (artifact.mime_type.startsWith("image/")) return <FileImage size={18} />;
  if (artifact.mime_type === "application/zip") return <FileArchive size={18} />;
  if (artifact.mime_type === "application/json") return <FileCode2 size={18} />;
  return <FileText size={18} />;
}

export function ArtifactGallery({ jobId, artifacts }: { jobId: string; artifacts: Artifact[] }) {
  const defaultId = useMemo(
    () => artifacts.find((item) => item.type === "grounding_pdf")?.id
      ?? artifacts.find((item) => item.type === "clean_markdown")?.id
      ?? artifacts[0]?.id
      ?? null,
    [artifacts],
  );
  const [selectedId, setSelectedId] = useState<string | null>(defaultId);
  const [text, setText] = useState("");
  const [textState, setTextState] = useState<"idle" | "loading" | "ready" | "error">("idle");

  useEffect(() => setSelectedId(defaultId), [jobId, defaultId]);

  const selected = artifacts.find((item) => item.id === selectedId) ?? null;
  const isText = Boolean(selected && (
    selected.mime_type.startsWith("text/") || selected.mime_type === "application/json"
  ));

  useEffect(() => {
    setText("");
    setTextState("idle");
    if (!selected?.preview_url || !isText || selected.size > 2 * 1024 * 1024) return;
    const controller = new AbortController();
    setTextState("loading");
    void fetch(apiResourceUrl(selected.preview_url), { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Preview unavailable");
        const value = await response.text();
        if (selected.mime_type !== "application/json") return value;
        return JSON.stringify(JSON.parse(value), null, 2);
      })
      .then((value) => {
        if (!controller.signal.aborted) {
          setText(value);
          setTextState("ready");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setTextState("error");
      });
    return () => controller.abort();
  }, [isText, selected?.id, selected?.mime_type, selected?.preview_url, selected?.size]);

  if (!artifacts.length) {
    return <section className="artifact-gallery"><div className="artifact-empty">Output files appear when parsing completes.</div></section>;
  }

  return <section className="artifact-gallery" aria-labelledby="output-files-title">
    <div className="artifact-heading"><div><h2 id="output-files-title">Output files</h2><p>Preview and download every public artifact produced by this job.</p></div><span>{artifacts.length} files</span></div>
    <div className="artifact-layout">
      <div className="artifact-list" role="list" aria-label="Generated files">
        {artifacts.map((artifact) => <div className={`artifact-row ${selected?.id === artifact.id ? "selected" : ""}`} role="listitem" key={artifact.id}>
          <button type="button" onClick={() => setSelectedId(artifact.id)} aria-pressed={selected?.id === artifact.id} aria-label={`Preview ${artifact.filename}`}>
            <i><ArtifactIcon artifact={artifact} /></i><span><strong>{artifact.filename}</strong><small>{LABELS[artifact.type] ?? artifact.type.replaceAll("_", " ")} · {formatSize(artifact.size)}</small></span><Eye size={15} />
          </button>
          <a href={artifactUrl(artifact)} download={artifact.filename} aria-label={`Download ${artifact.filename}`} title={`Download ${artifact.filename}`}><Download size={15} /></a>
        </div>)}
      </div>
      <div className="artifact-preview" aria-live="polite">
        {selected && <div className="artifact-preview-head"><div><strong>{LABELS[selected.type] ?? selected.filename}</strong><small>{selected.filename} · {formatSize(selected.size)}</small></div><a href={artifactUrl(selected)} download={selected.filename}><Download size={15} /> Download</a></div>}
        {selected?.mime_type === "application/pdf" && selected.preview_url && <iframe title={`${LABELS[selected.type] ?? selected.filename} preview`} src={apiResourceUrl(selected.preview_url)} sandbox="" />}
        {selected?.mime_type.startsWith("image/") && selected.preview_url && <div className="artifact-image">
          {/* Artifact URLs are authenticated runtime resources, not static Next images. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={apiResourceUrl(selected.preview_url)} alt={`${LABELS[selected.type] ?? "Artifact"} preview`} />
        </div>}
        {isText && textState === "loading" && <div className="artifact-message"><Loader2 className="spin" size={20} /> Loading preview…</div>}
        {isText && textState === "ready" && <pre>{text}</pre>}
        {isText && textState === "error" && <div className="artifact-message error">Preview could not be loaded. The file is still available to download.</div>}
        {selected && (!selected.preview_url || (isText && selected.size > 2 * 1024 * 1024)) && <div className="artifact-message"><FileArchive size={28} /><strong>This file is download-only</strong><p>{selected.size > 2 * 1024 * 1024 ? "Large artifacts are not loaded into the browser preview." : "Download the file to inspect its contents."}</p></div>}
      </div>
    </div>
  </section>;
}
