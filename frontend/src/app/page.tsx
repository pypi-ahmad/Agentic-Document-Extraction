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
  cancelParseJob,
  createParseJob,
  getParseJob,
  getParseTrace,
  listParseJobs,
  listParseReviews,
  type AgentTraceEvent,
  type AgenticParseJob,
  type ParseModel,
  type ParseReview,
  type AgenticParseSettings,
} from "@/lib/api";

const TERMINAL = new Set(["completed", "completed_with_warnings", "failed", "cancelled"]);
const CANCELLABLE = new Set(["queued", "inspecting", "processing", "assembling"]);
const THEME_STORAGE_KEY = "paperplane:theme:v1";

type Theme = "light" | "dark";
type WorkspaceTab = "configure" | "results";
type SessionPreview = DocumentSource & { jobId: string | null };

const MODEL_COPY: Record<ParseModel, string> = {
  "paperplane-ade-fast-latest": "Fast — one agent wave for straightforward documents",
  "paperplane-ade-latest": "Balanced — adaptive specialist review",
  "paperplane-ade-audit-latest": "Audit — maximum inspection depth",
};

function title(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatBytes(bytes: number) {
  return bytes < 1_048_576 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1_048_576).toFixed(1)} MB`;
}

export default function HomePage() {
  const [jobs, setJobs] = useState<AgenticParseJob[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("configure");
  const [file, setFile] = useState<File | null>(null);
  const [sessionPreview, setSessionPreview] = useState<SessionPreview | null>(null);
  const sessionPreviewUrl = useRef<string | null>(null);
  const [model, setModel] = useState<ParseModel>("paperplane-ade-latest");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<AgentTraceEvent[]>([]);
  const [reviews, setReviews] = useState<ParseReview[]>([]);
  const [theme, setTheme] = useState<Theme>("dark");

  const active = activeId ? jobs.find((item) => item.id === activeId) ?? null : null;

  const refresh = useCallback(async () => {
    const items = await listParseJobs();
    setJobs(items);
    setActiveId((current) => {
      if (current) return current;
      if (items[0]) setWorkspaceTab("results");
      return items[0]?.id ?? null;
    });
  }, []);

  useEffect(() => {
    void refresh().catch((reason: unknown) => {
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
      void getParseJob(active.id).then((updated) => {
        setJobs((items) => items.map((item) => item.id === updated.id ? updated : item));
      }).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active]);

  useEffect(() => {
    if (!active) {
      setTrace([]);
      setReviews([]);
      return;
    }
    const controller = new AbortController();
    void Promise.all([
      getParseTrace(active.id, controller.signal).catch(() => []),
      listParseReviews(active.id, controller.signal).catch(() => []),
    ]).then(([nextTrace, nextReviews]) => {
      if (!controller.signal.aborted) {
        setTrace(nextTrace);
        setReviews(nextReviews);
      }
    });
    return () => controller.abort();
  }, [active]);

  const documentSource = useMemo<DocumentSource | null>(() => {
    if (sessionPreview && ((!active && !sessionPreview.jobId) || active?.id === sessionPreview.jobId)) {
      return sessionPreview;
    }
    return active ? {
      url: active.source_preview_url ?? `/api/v2/parse/jobs/${active.id}/source`,
      mimeType: active.source_mime,
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
    const settings: AgenticParseSettings = { model };
    try {
      const created = await createParseJob(file, settings);
      setJobs((items) => [created, ...items]);
      setActiveId(created.id);
      setSessionPreview((current) => current ? { ...current, jobId: created.id } : current);
      setFile(null);
      setWorkspaceTab("results");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Parsing could not start");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel() {
    if (!active) return;
    try {
      const updated = await cancelParseJob(active.id);
      setJobs((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Parsing could not be stopped");
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
  }

  function startNewExtraction() {
    stageFile(null);
    setError(null);
  }

  function moveWorkspaceTab(current: WorkspaceTab, key: string) {
    const tabs: WorkspaceTab[] = ["configure", "results"];
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
          {(["configure", "results"] as WorkspaceTab[]).map((tab) => (
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
            <div className="panel-heading"><p>New parse</p><h1>Extract what the page proves.</h1><span>Configure a grounded multi-agent parse, then inspect every output beside its evidence.</span></div>
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
            <button className="primary" type="button" disabled={!file || submitting} onClick={() => void submit()}>{submitting ? <LoaderCircle className="spin" size={17} /> : <FileSearch size={17} />}Start parsing</button>
          </div>
        )}

        {workspaceTab === "results" && (
          <div className="workspace-scroll results-panel" role="tabpanel" id="workspace-panel-results" aria-labelledby="workspace-tab-results">
            {!active ? <div className="panel-empty"><FileSearch size={26} /><strong>No run selected</strong><span>Choose a run or start a new extraction.</span></div> : <>
              <div className="result-heading"><div><p>{MODEL_COPY[active.settings.model]}</p><h1>{active.original_filename}</h1><span>{active.page_count} pages · {formatBytes(active.source_size)}</span></div><div className={`status ${active.status}`}><i />{title(active.status)}</div></div>
              <div className="progress" role="progressbar" aria-label="Parse progress" aria-valuemin={0} aria-valuemax={active.page_count} aria-valuenow={active.completed_pages}><i style={{ width: `${active.page_count ? active.completed_pages / active.page_count * 100 : 0}%` }} /></div>
              <div className="metrics">
                <div><strong>{active.completed_pages}/{active.page_count}</strong><span>Pages parsed</span></div>
                <div><strong>{active.failed_pages}</strong><span>Page failures</span></div>
              </div>
              {active.error_message && <div className="run-error">{active.error_message}</div>}
              <ArtifactPreview jobId={active.id} artifacts={active.artifacts} reviews={reviews} trace={trace} />
              {CANCELLABLE.has(active.status) && <button className="stop" type="button" onClick={() => void cancel()}><Square size={13} />Stop parsing</button>}
            </>}
          </div>
        )}
      </section>
    </main>
  );
}
