"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, Download, RefreshCcw } from "lucide-react";
import {
  ApiError,
  artifactUrl,
  getPageDiagnostics,
  type PageCheckpoint,
  type PageDiagnostics,
  type ParseJob,
  type QualityScore,
  type QualityStatus,
  type RegionDecision,
} from "@/lib/api";

const STATUS_ORDER: QualityStatus[] = ["pass", "warn", "fail"];

function label(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "Not available";
}

function percent(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function clipped(value: string, limit = 180) {
  return value.length > limit ? `${value.slice(0, limit)}…` : value;
}

function StatusBadge({ status }: { status: QualityStatus | null }) {
  return <span className={`quality-badge ${status ?? "pending"}`}>{status ?? "pending"}</span>;
}

function ScoreGrid({ score }: { score: QualityScore }) {
  return (
    <div>
      <dl className="score-grid">
        <div><dt>Accuracy</dt><dd>{percent(score.extraction_accuracy)}</dd></div>
        <div><dt>Structure</dt><dd>{percent(score.structural_fidelity)}</dd></div>
        <div><dt>Completeness</dt><dd>{percent(score.completeness)}</dd></div>
        <div><dt>Markdown</dt><dd>{percent(score.markdown_consistency)}</dd></div>
        <div className="score-overall"><dt>Overall</dt><dd>{percent(score.overall)}</dd></div>
      </dl>
      {!!score.reasons.length && <ul className="score-reasons" aria-label="Quality score reasons">{score.reasons.map((reason, index) => <li key={index} title={reason}>{clipped(reason)}</li>)}</ul>}
    </div>
  );
}

function RegionDetail({ decision, index }: { decision: RegionDecision; index: number }) {
  const [open, setOpen] = useState(index === 0);
  const selected = decision.attempts[decision.selected_attempt_index];
  const contentId = `region-${index}-${decision.observation.region_id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  return (
    <article className="region-card">
      <button
        className="region-toggle"
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((value) => !value)}
      >
        <span><strong>{decision.observation.region_id}</strong><small>{label(decision.observation.region_type)}</small></span>
        <span><StatusBadge status={decision.final_status} /><small>{percent(selected?.score.overall)}</small><ChevronDown className={open ? "expanded" : ""} size={16} /></span>
      </button>
      {open && <div className="region-detail" id={contentId}>
        <dl className="plan-grid">
          <div><dt>Strategy</dt><dd>{label(decision.plan.strategy)}</dd></div>
          <div><dt>Expert</dt><dd>{label(decision.plan.expert)}</dd></div>
          <div><dt>Difficulty</dt><dd>{percent(decision.plan.difficulty)}</dd></div>
          <div><dt>Prompt variant</dt><dd>{label(decision.plan.prompt_variant)}</dd></div>
          <div><dt>Selected attempt</dt><dd>{selected ? `${selected.attempt} of ${decision.attempts.length}` : "—"}</dd></div>
        </dl>
        {!!decision.observation.risk_flags.length && <div className="risk-group"><strong>Observed risks</strong><div className="risk-list">{decision.observation.risk_flags.map((risk) => <span key={risk}>{clipped(risk, 80)}</span>)}</div></div>}
        {!!decision.plan.risk_flags.length && <div className="risk-group"><strong>Planner risks</strong><div className="risk-list">{decision.plan.risk_flags.map((risk) => <span key={risk}>{clipped(risk, 80)}</span>)}</div></div>}
        {decision.visual_verification && <div className="risk-group"><strong>Visual coordinate verification</strong><div className="risk-list"><span>{label(decision.visual_verification.status)}</span>{decision.visual_verification.methods.map((method) => <span key={method}>{label(method)}</span>)}</div>{!!decision.visual_verification.reasons.length && <ul className="warning-list">{decision.visual_verification.reasons.map((reason, reasonIndex) => <li key={reasonIndex} title={reason}>{clipped(reason)}</li>)}</ul>}</div>}
        {selected && <ScoreGrid score={selected.score} />}
        <div className="attempt-list">
          {decision.attempts.map((attempt, attemptIndex) => <section className={`attempt ${attemptIndex === decision.selected_attempt_index ? "selected" : ""}`} key={attempt.attempt}>
            <div className="attempt-head"><strong>Attempt {attempt.attempt}{attemptIndex === decision.selected_attempt_index ? " · selected" : ""}</strong><StatusBadge status={attempt.verdict} /></div>
            <dl className="attempt-meta">
              <div><dt>Route</dt><dd>{label(attempt.strategy)}</dd></div>
              <div><dt>Expert</dt><dd>{label(attempt.expert)}</dd></div>
              <div><dt>Prompt</dt><dd>{attempt.prompt_id} v{attempt.prompt_version} · {label(attempt.prompt_variant)}</dd></div>
              <div><dt>Latency</dt><dd>{Math.round(attempt.latency_ms)} ms</dd></div>
              <div><dt>Tokens</dt><dd>{attempt.eval_count ?? "—"} output / {attempt.prompt_eval_count ?? "—"} prompt</dd></div>
              <div><dt>Reason</dt><dd title={attempt.reason}>{clipped(attempt.reason)}</dd></div>
              {attempt.repair_hint && <div className="meta-wide"><dt>Repair hint</dt><dd title={attempt.repair_hint}>{clipped(attempt.repair_hint)}</dd></div>}
            </dl>
            {!!attempt.warnings.length && <ul className="warning-list">{attempt.warnings.map((warning, warningIndex) => <li key={`${attempt.attempt}-${warningIndex}`} title={warning}>{clipped(warning)}</li>)}</ul>}
          </section>)}
        </div>
      </div>}
    </article>
  );
}

function PageButton({ page, selected, onSelect }: { page: PageCheckpoint; selected: boolean; onSelect: () => void }) {
  return <button className={`page-row ${selected ? "selected" : ""}`} type="button" onClick={onSelect} aria-pressed={selected}>
    <span><strong>Page {page.page_number}</strong><small>{label(page.stage ?? page.status)}</small></span>
    <span><StatusBadge status={page.quality_status} /><small>{percent(page.quality_score)}</small></span>
  </button>;
}

export function QualityDiagnostics({ job, progress }: { job: ParseJob; progress: number }) {
  const pages = useMemo(() => [...job.pages].sort((a, b) => a.page_number - b.page_number), [job.pages]);
  const availablePages = useMemo(() => pages.filter((page) => page.diagnostics_url), [pages]);
  const [pageNumber, setPageNumber] = useState<number | null>(availablePages[0]?.page_number ?? pages[0]?.page_number ?? null);
  const [diagnostics, setDiagnostics] = useState<PageDiagnostics | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "unavailable" | "error">("idle");
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const diagnosticsArtifact = job.artifacts.find((artifact) => artifact.type === "diagnostics");
  const selectedPage = pages.find((page) => page.page_number === pageNumber);
  const refreshKey = selectedPage ? `${selectedPage.diagnostics_url}:${selectedPage.stage}:${selectedPage.attempts}:${selectedPage.repair_count}:${selectedPage.quality_score}` : "none";

  useEffect(() => {
    if (pageNumber != null && pages.some((page) => page.page_number === pageNumber)) return;
    setPageNumber(availablePages[0]?.page_number ?? pages[0]?.page_number ?? null);
  }, [availablePages, pageNumber, pages]);

  useEffect(() => {
    if (!selectedPage?.diagnostics_url || pageNumber == null) {
      setDiagnostics(null);
      setState("unavailable");
      return;
    }
    const controller = new AbortController();
    setState("loading");
    setError("");
    void getPageDiagnostics(job.id, pageNumber, controller.signal).then((payload) => {
      setDiagnostics(payload);
      setState("ready");
    }).catch((caught: unknown) => {
      if (controller.signal.aborted) return;
      setDiagnostics(null);
      if (caught instanceof ApiError && caught.status === 404) setState("unavailable");
      else { setState("error"); setError(caught instanceof Error ? caught.message : "Diagnostics could not be loaded."); }
    });
    return () => controller.abort();
  }, [job.id, pageNumber, refreshKey, reload, selectedPage?.diagnostics_url]);

  const counts = STATUS_ORDER.reduce((result, status) => {
    result[status] = pages.filter((page) => page.quality_status === status).length;
    return result;
  }, { pass: 0, warn: 0, fail: 0 });
  const scores = pages.flatMap((page) => page.quality_score == null ? [] : [page.quality_score]);
  const average = scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length : null;
  const retries = pages.reduce((sum, page) => sum + Math.max(0, page.attempts - 1), 0);
  const repairs = pages.reduce((sum, page) => sum + page.repair_count, 0);
  const retry = useCallback(() => setReload((value) => value + 1), []);

  return <section className="quality-dashboard" aria-labelledby="quality-title">
    <div className="quality-head">
      <div><h2 id="quality-title">Extraction quality</h2><p>{progress}% complete · {label(job.settings.input_mode)}</p></div>
      {diagnosticsArtifact && <a className="secondary-download" href={artifactUrl(diagnosticsArtifact)}><Download size={15} /> diagnostics.json</a>}
    </div>
    <div className="progress-track" aria-label={`${progress}% complete`}><i style={{ width: `${progress}%` }} /></div>
    <div className="quality-metrics">
      <div><span>Pass / warn / fail</span><strong>{counts.pass} / {counts.warn} / {counts.fail}</strong></div>
      <div><span>Average score</span><strong>{percent(average)}</strong></div>
      <div><span>Retries / repairs</span><strong>{retries} / {repairs}</strong></div>
      <div><span>Warnings</span><strong>{job.warning_count}</strong></div>
      <div><span>Primary parser</span><strong title={job.model_name ?? "Not recorded"}>{job.model_name ?? "Not recorded"}</strong></div>
      <div><span>Review model</span><strong title={job.review_model_name ?? "Not recorded"}>{job.review_model_name ?? "Not recorded"}</strong></div>
    </div>
    <div className="diagnostics-layout">
      <nav className="page-list" aria-label="Page diagnostics">
        {pages.map((page) => <PageButton key={page.page_number} page={page} selected={page.page_number === pageNumber} onSelect={() => setPageNumber(page.page_number)} />)}
        {!pages.length && <p className="diagnostics-empty">Pages will appear as processing begins.</p>}
      </nav>
      <div className="diagnostics-detail" aria-live="polite">
        {state === "loading" && <div className="diagnostics-skeleton" aria-busy="true" aria-label="Loading page diagnostics"><i /><i /><i /></div>}
        {state === "unavailable" && <div className="diagnostics-empty"><strong>Diagnostics not available yet</strong><p>This page has not reached a verified checkpoint.</p></div>}
        {state === "error" && <div className="diagnostics-empty error"><strong>Could not load diagnostics</strong><p>{clipped(error)}</p><button type="button" onClick={retry}><RefreshCcw size={14} /> Retry</button></div>}
        {state === "ready" && diagnostics && <>
          <div className="page-quality-head"><div><strong>Page {diagnostics.page_number}</strong><small>{label(diagnostics.stage)} · {diagnostics.region_decisions.length} regions · {diagnostics.repair_count} repairs</small></div><StatusBadge status={diagnostics.quality_status} /></div>
          {diagnostics.quality_score && <ScoreGrid score={diagnostics.quality_score} />}
          {!!diagnostics.warnings.length && <ul className="warning-list page-warnings">{diagnostics.warnings.map((warning, index) => <li key={index} title={warning}>{clipped(warning)}</li>)}</ul>}
          <div className="region-list">{diagnostics.region_decisions.map((decision, index) => <RegionDetail key={decision.observation.region_id} decision={decision} index={index} />)}</div>
          {!diagnostics.region_decisions.length && <div className="diagnostics-empty"><strong>No regions recorded</strong><p>The page checkpoint contains no region decisions.</p></div>}
        </>}
      </div>
    </div>
  </section>;
}
