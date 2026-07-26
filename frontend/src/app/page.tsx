"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Box, CheckCircle2, Download, FileSearch, LoaderCircle, ShieldCheck, Square, Upload } from "lucide-react";

import {
  artifactUrl,
  cancelV2Job,
  createV2Job,
  evaluateV2Job,
  getV2Job,
  listExtractionSchemas,
  listV2Jobs,
  type ExtractionSchema,
  type V2Artifact,
  type V2Job,
  type V2EvaluationReport,
  type V2Mode,
  type V2Settings,
} from "@/lib/api";

const TERMINAL = new Set(["completed", "completed_with_warnings", "failed", "cancelled"]);
const CANCELLABLE = new Set(["queued", "inspecting", "processing", "assembling"]);

const MODE_COPY: Record<V2Mode, string> = {
  economy: "Fast draft with deterministic grounding",
  balanced: "Selective crop verification for uncertain regions",
  audit: "Maximum inspection depth and high-resolution crops",
};

const ARTIFACT_NAMES: Record<string, string> = {
  markdown: "Markdown",
  clean_markdown: "Markdown",
  document_json: "Grounded JSON",
  annotated_pdf: "Annotated PDF",
  usage_json: "Usage report",
  usage: "Usage report",
  extraction_json: "Schema extraction",
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

function ArtifactLink({ artifact }: { artifact: V2Artifact }) {
  return (
    <a className="artifact" href={artifactUrl(artifact)}>
      <span><Download size={16} />{ARTIFACT_NAMES[artifact.type] ?? title(artifact.type)}</span>
      <small>{formatBytes(artifact.size)}</small>
    </a>
  );
}

export default function HomePage() {
  const [jobs, setJobs] = useState<V2Job[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<V2Mode>("balanced");
  const [segment, setSegment] = useState(true);
  const [schemaId, setSchemaId] = useState<string>("");
  const [schemas, setSchemas] = useState<ExtractionSchema[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [labels, setLabels] = useState<File | null>(null);
  const [evaluation, setEvaluation] = useState<V2EvaluationReport | null>(null);

  const active = jobs.find((item) => item.id === activeId) ?? jobs[0] ?? null;

  const refresh = useCallback(async () => {
    const items = await listV2Jobs();
    setJobs(items);
    setActiveId((current) => current ?? items[0]?.id ?? null);
  }, []);

  useEffect(() => {
    void Promise.all([refresh(), listExtractionSchemas().then(setSchemas)]).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Backend is unavailable");
    });
  }, [refresh]);

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

  async function submit() {
    if (!file) return;
    setSubmitting(true);
    setError(null);
    const settings: V2Settings = {
      mode,
      segment_documents: segment,
      extraction_schema_id: schemaId || null,
    };
    try {
      const created = await createV2Job(file, settings);
      setJobs((items) => [created, ...items]);
      setActiveId(created.id);
      setFile(null);
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

  return (
    <main>
      <header className="masthead">
        <div className="brand"><Box size={21} /><strong>Paperplane</strong><span>Grounded document extraction</span></div>
        <div className="model-chain"><span>Draft <b>gpt-5.6-luna</b></span><i>→</i><span>Verify <b>gpt-5.6-terra</b></span></div>
      </header>

      <section className="hero">
        <div><p className="eyebrow">OpenAI document intelligence</p><h1>Extract what the page proves.</h1><p>Layout-aware Markdown and structured JSON with page coordinates, crop evidence, reading order, and explicit abstention.</p></div>
        <div className="trust"><ShieldCheck size={22} /><span><strong>Auditable by design</strong>Every value traces to a verified source region.</span></div>
      </section>

      {error && <div role="alert" className="error">{error}</div>}

      <section className="workbench">
        <aside className="setup">
          <div className="section-title"><span>01</span><div><strong>Configure</strong><small>One pipeline, three quality levels</small></div></div>
          <label className="field">Processing mode
            <select aria-label="Processing mode" value={mode} onChange={(event) => setMode(event.target.value as V2Mode)}>
              <option value="economy">Economy — fast</option>
              <option value="balanced">Balanced — recommended</option>
              <option value="audit">Audit — maximum accuracy</option>
            </select>
            <small>{MODE_COPY[mode]}</small>
          </label>
          <label className="field">Extraction schema
            <select value={schemaId} onChange={(event) => setSchemaId(event.target.value)}>
              <option value="">Markdown + grounded JSON</option>
              {schemas.map((schema) => <option key={schema.id} value={schema.id}>{schema.name}</option>)}
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={segment} onChange={(event) => setSegment(event.target.checked)} /><span><strong>Segment mixed documents</strong><small>Classify repeated document instances and identifiers.</small></span></label>
          <label className="dropzone">
            <input aria-label="Choose document" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            <Upload size={25} /><strong>{file?.name ?? "Choose a document"}</strong><small>PDF, PNG, JPEG, WebP, or TIFF</small>
          </label>
          <button className="primary" type="button" disabled={!file || submitting} onClick={() => void submit()}>{submitting ? <LoaderCircle className="spin" size={17} /> : <FileSearch size={17} />}Start extraction</button>
        </aside>

        <section className="runs">
          <div className="section-title"><span>02</span><div><strong>Inspect</strong><small>Live progress and grounded exports</small></div></div>
          <div className="run-layout">
            <nav className="job-list" aria-label="Extraction jobs">
              {jobs.map((item) => <button type="button" key={item.id} className={active?.id === item.id ? "active" : ""} onClick={() => setActiveId(item.id)}><span>{item.original_filename}</span><small>{item.completed_pages}/{item.page_count} pages · {title(item.status)}</small></button>)}
              {!jobs.length && <div className="empty"><FileSearch size={24} /><span>No extraction runs yet.</span></div>}
            </nav>
            <article className="run-detail">
              {!active ? <div className="empty large"><span>Upload a document to begin.</span></div> : <>
                <div className="run-head"><div><p className="eyebrow">{active.settings.mode} mode</p><h2>{active.original_filename}</h2><p>{active.page_count} pages · {formatBytes(active.source_size)}</p></div><div className={`status ${active.status}`}><i />{title(active.status)}</div></div>
                <div className="progress"><i style={{ width: `${active.page_count ? active.completed_pages / active.page_count * 100 : 0}%` }} /></div>
                <div className="metrics">
                  <div><strong>{active.completed_pages}/{active.page_count}</strong><span>Pages grounded</span></div>
                  <div><strong>{cacheRate}% cache hit</strong><span>Prompt input reuse</span></div>
                  <div><strong>{metric(active.usage, ["output_tokens"]).toLocaleString()}</strong><span>Output tokens</span></div>
                  <div><strong>${metric(active.usage, ["estimated_cost_usd", "total_usd"]).toFixed(4)}</strong><span>Estimated cost</span></div>
                </div>
                {active.error_message && <div className="error">{active.error_message}</div>}
                {active.artifacts.length > 0 && <div className="artifacts"><div><CheckCircle2 size={18} /><strong>Grounded outputs</strong></div>{active.artifacts.map((artifact) => <ArtifactLink key={artifact.id} artifact={artifact} />)}</div>}
                {active.artifacts.some((item) => item.type === "annotated_pdf") && <div className="audit-tools">
                  <button type="button" className="secondary" onClick={() => setPreviewOpen((value) => !value)}>Preview annotated PDF</button>
                  {previewOpen && <iframe title="Annotated PDF preview" src={artifactUrl(active.artifacts.find((item) => item.type === "annotated_pdf")!)} />}
                </div>}
                {TERMINAL.has(active.status) && <div className="evaluation">
                  <strong>Evaluate grounded output</strong>
                  <p>Upload a labeled <code>paperplane-document/v2</code> JSON file.</p>
                  <label>Ground-truth labels<input aria-label="Ground-truth labels" type="file" accept="application/json,.json" onChange={(event) => setLabels(event.target.files?.[0] ?? null)} /></label>
                  <button type="button" className="secondary" disabled={!labels} onClick={() => void evaluate()}>Run evaluation</button>
                  {evaluation && <span>{(evaluation.metrics.macro_score * 100).toFixed(1)}% macro score</span>}
                </div>}
                {CANCELLABLE.has(active.status) && <button className="stop" type="button" onClick={() => void cancel()}><Square size={13} />Stop extraction</button>}
              </>}
            </article>
          </div>
        </section>
      </section>
    </main>
  );
}
