"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  FilePlus2,
  FileSearch,
  Gauge,
  LoaderCircle,
  Moon,
  PanelLeft,
  Square,
  Sun,
  Upload,
} from "lucide-react";

import { ArtifactPreview } from "@/components/v2/ArtifactPreview";
import { DocumentCanvas, type DocumentSource } from "@/components/v2/DocumentCanvas";
import { RunHistory } from "@/components/v2/RunHistory";
import {
  artifactUrl,
  cancelV2Job,
  createV2Job,
  evaluateV2Job,
  getV2Job,
  listExtractionSchemas,
  listV2Jobs,
  type ExtractionSchema,
  type V2EvaluationReport,
  type V2Job,
  type V2Mode,
  type V2Settings,
} from "@/lib/api";

const TERMINAL = new Set(["completed", "completed_with_warnings", "failed", "cancelled"]);
const CANCELLABLE = new Set(["queued", "inspecting", "processing", "assembling"]);
const THEME_STORAGE_KEY = "paperplane:theme:v1";

type Theme = "light" | "dark";
type WorkspaceTab = "configure" | "results" | "evaluate";
type SessionPreview = DocumentSource & { jobId: string | null };

const MODE_COPY: Record<V2Mode, string> = {
  economy: "Fast draft with deterministic grounding",
  balanced: "Selective crop verification for uncertain regions",
  audit: "Maximum inspection depth and high-resolution crops",
};

function title(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatBytes(bytes: number) {
  return bytes < 1_048_576 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1_048_576).toFixed(1)} MB`;
}

function metric(usage: Record<string, number> | null, keys: string[]) {
  for (const key of keys) if (typeof usage?.[key] === "number") return usage[key];
  return 0;
}

export default function HomePage() {
  const [jobs, setJobs] = useState<V2Job[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("configure");
  const [file, setFile] = useState<File | null>(null);
  const [sessionPreview, setSessionPreview] = useState<SessionPreview | null>(null);
  const sessionPreviewUrl = useRef<string | null>(null);
  const [mode, setMode] = useState<V2Mode>("balanced");
  const [segment, setSegment] = useState(true);
  const [schemaId, setSchemaId] = useState("");
  const [schemas, setSchemas] = useState<ExtractionSchema[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [labels, setLabels] = useState<File | null>(null);
  const [evaluation, setEvaluation] = useState<V2EvaluationReport | null>(null);
  const [theme, setTheme] = useState<Theme>("dark");

  const active = activeId ? jobs.find((item) => item.id === activeId) ?? null : null;

  const refresh = useCallback(async () => {
    const items = await listV2Jobs();
    setJobs(items);
    setActiveId((current) => {
      if (current) return current;
      if (items[0]) setWorkspaceTab("results");
      return items[0]?.id ?? null;
    });
  }, []);

  useEffect(() => {
    void Promise.all([refresh(), listExtractionSchemas().then(setSchemas)]).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Backend is unavailable");
    });
  }, [refresh]);

  useEffect(() => {
    const initial = document.documentElement.dataset.theme;
    setTheme(initial === "light" ? "light" : "dark");
  }, []);

  useEffect(() => () => {
    if (sessionPreviewUrl.current) URL.revokeObjectURL(sessionPreviewUrl.current);
  }, []);

  useEffect(() => {
    if (!active || TERMINAL.has(active.status)) return;
    const timer = window.setInterval(() => {
      void getV2Job(active.id).then((updated) => {
        setJobs((items) => items.map((item) => item.id === updated.id ? updated : item));
      }).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active]);

  const cacheRate = useMemo(() => {
    const input = metric(active?.usage ?? null, ["input_tokens"]);
    const cached = metric(active?.usage ?? null, ["cached_input_tokens", "input_tokens_details.cached_tokens"]);
    return input ? Math.round(cached / input * 100) : 0;
  }, [active]);

  const documentSource = useMemo<DocumentSource | null>(() => {
    if (sessionPreview && ((!active && !sessionPreview.jobId) || active?.id === sessionPreview.jobId)) {
      return sessionPreview;
    }
    const annotated = active?.artifacts.find((artifact) => artifact.type === "annotated_pdf");
    return annotated && active ? {
      url: artifactUrl(annotated),
      mimeType: annotated.mime_type,
      label: active.original_filename,
      remote: true,
    } : null;
  }, [active, sessionPreview]);

  function stageFile(next: File | null) {
    if (sessionPreviewUrl.current) URL.revokeObjectURL(sessionPreviewUrl.current);
    sessionPreviewUrl.current = null;
    setFile(next);
    setActiveId(null);
    setWorkspaceTab("configure");
    if (!next) {
      setSessionPreview(null);
      return;
    }
    const url = URL.createObjectURL(next);
    sessionPreviewUrl.current = url;
    setSessionPreview({ url, mimeType: next.type || "application/pdf", label: next.name, remote: false, jobId: null });
  }

  async function submit() {
    if (!file) return;
    setSubmitting(true);
    setError(null);
    const settings: V2Settings = { mode, segment_documents: segment, extraction_schema_id: schemaId || null };
    try {
      const created = await createV2Job(file, settings);
      setJobs((items) => [created, ...items]);
      setActiveId(created.id);
      setSessionPreview((current) => current ? { ...current, jobId: created.id } : current);
      setFile(null);
      setWorkspaceTab("results");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Extraction could not start");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel() {
    if (!active) return;
    try {
      const updated = await cancelV2Job(active.id);
      setJobs((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Extraction could not be stopped");
    }
  }

  async function evaluate() {
    if (!active || !labels) return;
    setError(null);
    try {
      setEvaluation(await evaluateV2Job(active.id, labels));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Evaluation failed");
    }
  }

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    setTheme(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // The selected theme still applies for this page when storage is blocked.
    }
  }

  function selectRun(jobId: string) {
    setActiveId(jobId);
    setWorkspaceTab("results");
    setEvaluation(null);
  }

  function startNewExtraction() {
    stageFile(null);
    setLabels(null);
    setEvaluation(null);
    setError(null);
  }

  function moveWorkspaceTab(current: WorkspaceTab, key: string) {
    const tabs: WorkspaceTab[] = ["configure", "results", "evaluate"];
    const index = tabs.indexOf(current);
    const next = key === "Home" ? tabs[0] : key === "End" ? tabs.at(-1) : key === "ArrowRight" ? tabs[(index + 1) % tabs.length] : key === "ArrowLeft" ? tabs[(index - 1 + tabs.length) % tabs.length] : null;
    if (!next) return;
    setWorkspaceTab(next);
    document.getElementById(`workspace-tab-${next}`)?.focus();
  }

  return (
    <main className="studio-shell">
      <header className="masthead">
        <div className="brand"><Box size={20} /><strong>Paperplane</strong><span>Grounded document extraction</span></div>
        <div className="masthead-actions">
          <div className="model-chain"><span>Draft <b>gpt-5.6-luna</b></span><i>→</i><span>Verify <b>gpt-5.6-terra</b></span></div>
          <button className="theme-toggle" type="button" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={toggleTheme}>
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>

      <aside className="tool-rail" aria-label="Workspace tools">
        <div className="rail-mark"><Box size={18} /></div>
        <button type="button" className={!active && workspaceTab === "configure" ? "active" : ""} aria-label="New extraction" onClick={startNewExtraction}><FilePlus2 size={18} /></button>
        <div className="rail-button" title="Extraction runs"><PanelLeft size={18} /></div>
        <div className="rail-spacer" />
        <div className="rail-proof" title="Grounded evidence enabled"><Gauge size={17} /></div>
      </aside>

      <RunHistory jobs={jobs} activeId={activeId} onSelect={selectRun} />

      <DocumentCanvas source={documentSource} status={active?.status ?? null} errorMessage={active?.error_message ?? null} />

      <section className="workspace-panel" aria-label="Extraction workspace">
        <div className="workspace-tabs" role="tablist" aria-label="Workspace">
          {(["configure", "results", "evaluate"] as WorkspaceTab[]).map((tab) => (
            <button
              type="button"
              role="tab"
              key={tab}
              id={`workspace-tab-${tab}`}
              aria-selected={workspaceTab === tab}
              aria-controls={`workspace-panel-${tab}`}
              tabIndex={workspaceTab === tab ? 0 : -1}
              onClick={() => setWorkspaceTab(tab)}
              onKeyDown={(event) => moveWorkspaceTab(tab, event.key)}
            >
              {title(tab)}
            </button>
          ))}
        </div>

        {error && <div role="alert" className="error">{error}</div>}

        {workspaceTab === "configure" && (
          <div className="workspace-scroll configure-panel" role="tabpanel" id="workspace-panel-configure" aria-labelledby="workspace-tab-configure">
            <div className="panel-heading"><p>New extraction</p><h1>Extract what the page proves.</h1><span>Configure one grounded OpenAI pipeline, then inspect every output beside its evidence.</span></div>
            <label className="field">Processing mode
              <select aria-label="Processing mode" value={mode} onChange={(event) => setMode(event.target.value as V2Mode)}>
                <option value="economy">Economy — fast</option>
                <option value="balanced">Balanced — recommended</option>
                <option value="audit">Audit — maximum accuracy</option>
              </select>
              <small>{MODE_COPY[mode]}</small>
            </label>
            <label className="field">Extraction schema
              <select aria-label="Extraction schema" value={schemaId} onChange={(event) => setSchemaId(event.target.value)}>
                <option value="">Markdown + grounded JSON</option>
                {schemas.map((schema) => <option key={schema.id} value={schema.id}>{schema.name}</option>)}
              </select>
            </label>
            <label className="check"><input type="checkbox" checked={segment} onChange={(event) => setSegment(event.target.checked)} /><span><strong>Segment mixed documents</strong><small>Classify repeated document instances and identifiers.</small></span></label>
            <label className="dropzone">
              <input aria-label="Choose document" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff" onChange={(event) => stageFile(event.target.files?.[0] ?? null)} />
              <Upload size={24} /><strong>{file?.name ?? "Choose a document"}</strong><small>PDF, PNG, JPEG, WebP, or TIFF</small>
            </label>
            <button className="primary" type="button" disabled={!file || submitting} onClick={() => void submit()}>{submitting ? <LoaderCircle className="spin" size={17} /> : <FileSearch size={17} />}Start extraction</button>
          </div>
        )}

        {workspaceTab === "results" && (
          <div className="workspace-scroll results-panel" role="tabpanel" id="workspace-panel-results" aria-labelledby="workspace-tab-results">
            {!active ? <div className="panel-empty"><FileSearch size={26} /><strong>No run selected</strong><span>Choose a run or start a new extraction.</span></div> : <>
              <div className="result-heading"><div><p>{active.settings.mode} mode</p><h1>{active.original_filename}</h1><span>{active.page_count} pages · {formatBytes(active.source_size)}</span></div><div className={`status ${active.status}`}><i />{title(active.status)}</div></div>
              <div className="progress" role="progressbar" aria-label="Extraction progress" aria-valuemin={0} aria-valuemax={active.page_count} aria-valuenow={active.completed_pages}><i style={{ width: `${active.page_count ? active.completed_pages / active.page_count * 100 : 0}%` }} /></div>
              <div className="metrics">
                <div><strong>{active.completed_pages}/{active.page_count}</strong><span>Pages grounded</span></div>
                <div><strong>{cacheRate}% cache hit</strong><span>Prompt input reuse</span></div>
                <div><strong>{metric(active.usage, ["output_tokens"]).toLocaleString()}</strong><span>Output tokens</span></div>
                <div><strong>${metric(active.usage, ["estimated_cost_usd", "total_usd"]).toFixed(4)}</strong><span>Estimated cost</span></div>
              </div>
              {active.error_message && <div className="run-error">{active.error_message}</div>}
              <ArtifactPreview jobId={active.id} artifacts={active.artifacts} />
              {CANCELLABLE.has(active.status) && <button className="stop" type="button" onClick={() => void cancel()}><Square size={13} />Stop extraction</button>}
            </>}
          </div>
        )}

        {workspaceTab === "evaluate" && (
          <div className="workspace-scroll evaluate-panel" role="tabpanel" id="workspace-panel-evaluate" aria-labelledby="workspace-tab-evaluate">
            <div className="panel-heading"><p>Quality benchmark</p><h1>Evaluate grounded output</h1><span>Compare this run against labeled Paperplane document JSON.</span></div>
            {!active ? <div className="panel-empty"><span>Select a completed run to evaluate.</span></div> : !TERMINAL.has(active.status) ? <div className="panel-empty"><span>Evaluation becomes available when extraction reaches a terminal state.</span></div> : <>
              <label className="evaluation-upload">Ground-truth labels<input aria-label="Ground-truth labels" type="file" accept="application/json,.json" onChange={(event) => setLabels(event.target.files?.[0] ?? null)} /></label>
              <button type="button" className="secondary" disabled={!labels} onClick={() => void evaluate()}>Run evaluation</button>
              {evaluation && <div className="evaluation-score"><strong>{(evaluation.metrics.macro_score * 100).toFixed(1)}% macro score</strong></div>}
            </>}
          </div>
        )}
      </section>
    </main>
  );
}
