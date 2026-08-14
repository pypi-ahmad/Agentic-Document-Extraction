"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Box, FilePlus2, FileSearch, Gauge, LoaderCircle, Moon, Sun, Upload } from "lucide-react";

import { DocumentCanvas, type DocumentSource } from "@/components/v2/DocumentCanvas";
import { parseDocument, type ParseModel, type ParseNode, type ParseResponse } from "@/lib/api";

const THEME_STORAGE_KEY = "paperplane:theme:v1";
const MODEL_COPY: Record<ParseModel, string> = {
  "paperplane-ade-fast-latest": "Fast — straightforward documents",
  "paperplane-ade-latest": "Balanced — adaptive verification",
  "paperplane-ade-audit-latest": "Audit — maximum inspection depth",
};

type Theme = "light" | "dark";
type WorkspaceTab = "configure" | "results";
type ResultView = "markdown" | "json";

function countBlocks(node: ParseNode): number {
  return (node.type === "document" || node.type === "page" ? 0 : 1)
    + node.children.reduce((total, child) => total + countBlocks(child), 0);
}

export default function HomePage() {
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("configure");
  const [resultView, setResultView] = useState<ResultView>("markdown");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<DocumentSource | null>(null);
  const previewUrl = useRef<string | null>(null);
  const [model, setModel] = useState<ParseModel>("paperplane-ade-latest");
  const [result, setResult] = useState<ParseResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
    return () => {
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    };
  }, []);

  const blockCount = useMemo(() => result ? countBlocks(result.structure) : 0, [result]);

  function stageFile(next: File | null) {
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = null;
    setFile(next);
    setResult(null);
    setError(null);
    setWorkspaceTab("configure");
    if (!next) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(next);
    previewUrl.current = url;
    setPreview({ url, mimeType: next.type || "application/pdf", label: next.name, remote: false });
  }

  async function submit() {
    if (!file) return;
    setSubmitting(true);
    setError(null);
    try {
      setResult(await parseDocument(file, model));
      setWorkspaceTab("results");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Parsing failed");
    } finally {
      setSubmitting(false);
    }
  }

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    setTheme(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // The selected theme still applies when storage is blocked.
    }
  }

  return (
    <main className="studio-shell">
      <header className="masthead">
        <div className="brand"><Box size={20} /><strong>Paperplane</strong><span>Stateless document extraction</span></div>
        <div className="masthead-actions">
          <div className="model-chain"><span>Draft <b>gpt-5.6-luna</b></span><i>→</i><span>Verify <b>gpt-5.6-terra</b></span></div>
          <button className="theme-toggle" type="button" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={toggleTheme}>
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>

      <aside className="tool-rail" aria-label="Workspace tools">
        <div className="rail-mark"><Box size={18} /></div>
        <button type="button" className={workspaceTab === "configure" ? "active" : ""} aria-label="New extraction" onClick={() => stageFile(null)}><FilePlus2 size={18} /></button>
        <div className="rail-spacer" />
        <div className="rail-proof" title="Grounded evidence enabled"><Gauge size={17} /></div>
      </aside>

      <DocumentCanvas source={preview} status={submitting ? "processing" : result ? "completed" : null} errorMessage={error} />

      <section className="workspace-panel" aria-label="Extraction workspace">
        <div className="workspace-tabs" role="tablist" aria-label="Workspace">
          {(["configure", "results"] as WorkspaceTab[]).map((tab) => (
            <button type="button" role="tab" key={tab} aria-selected={workspaceTab === tab} onClick={() => setWorkspaceTab(tab)}>
              {tab === "configure" ? "Configure" : "Results"}
            </button>
          ))}
        </div>

        {error && <div role="alert" className="error">{error}</div>}

        {workspaceTab === "configure" && (
          <div className="workspace-scroll configure-panel" role="tabpanel">
            <div className="panel-heading"><p>New parse</p><h1>Extract what the page proves.</h1><span>Choose a document and receive grounded Markdown and JSON directly.</span></div>
            <label className="field">Processing model
              <select aria-label="Processing model" value={model} onChange={(event) => setModel(event.target.value as ParseModel)}>
                <option value="paperplane-ade-fast-latest">Fast</option>
                <option value="paperplane-ade-latest">Balanced — recommended</option>
                <option value="paperplane-ade-audit-latest">Audit</option>
              </select>
              <small>{MODEL_COPY[model]}</small>
            </label>
            <label className="dropzone">
              <input aria-label="Choose document" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff" onChange={(event) => stageFile(event.target.files?.[0] ?? null)} />
              <Upload size={24} /><strong>{file?.name ?? "Choose a document"}</strong><small>PDF, PNG, JPEG, WebP, or TIFF</small>
            </label>
            <button className="primary" type="button" disabled={!file || submitting} onClick={() => void submit()}>
              {submitting ? <LoaderCircle className="spin" size={17} /> : <FileSearch size={17} />}
              {submitting ? "Parsing…" : "Parse document"}
            </button>
          </div>
        )}

        {workspaceTab === "results" && (
          <div className="workspace-scroll results-panel" role="tabpanel">
            {!result ? <div className="panel-empty"><FileSearch size={26} /><strong>No result yet</strong><span>Choose a document and parse it.</span></div> : <>
              <div className="result-heading"><div><p>{MODEL_COPY[model]}</p><h1>{file?.name ?? "Document"}</h1></div><div className="status completed"><i />Completed</div></div>
              <div className="metrics">
                <div><strong>{result.metadata.page_count}</strong><span>Pages</span></div>
                <div><strong>{blockCount}</strong><span>Blocks</span></div>
                <div><strong>{result.metadata.output_characters}</strong><span>Characters</span></div>
                <div><strong>{result.metadata.duration_ms ?? 0} ms</strong><span>Duration</span></div>
              </div>
              <div className="result-tabs">
                <button type="button" className={resultView === "markdown" ? "active" : ""} onClick={() => setResultView("markdown")}>Markdown</button>
                <button type="button" className={resultView === "json" ? "active" : ""} onClick={() => setResultView("json")}>JSON</button>
              </div>
              <pre className="result-output">{resultView === "markdown" ? result.markdown : JSON.stringify(result, null, 2)}</pre>
            </>}
          </div>
        )}
      </section>
    </main>
  );
}
