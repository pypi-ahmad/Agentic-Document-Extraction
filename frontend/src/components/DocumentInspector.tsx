"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { Check, Loader2, RefreshCw, Search, TriangleAlert } from "lucide-react";
import {
  apiResourceUrl,
  getDocumentTree,
  getPageInspection,
  getQualityReport,
  requestReprocess,
  type DocumentTreeItem,
  type PageInspection,
  type ParseJob,
  type QualityReport,
} from "@/lib/api";

export function DocumentInspector({ job, markdown, onJobChanged }: { job: ParseJob; markdown: string; onJobChanged: () => void }) {
  const firstPage = job.pages.find((page) => page.status === "completed")?.page_number ?? job.settings.start_page;
  const [page, setPage] = useState(firstPage);
  const [inspection, setInspection] = useState<PageInspection | null>(null);
  const [tree, setTree] = useState<DocumentTreeItem[]>([]);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"evidence" | "markdown" | "quality">("evidence");
  const [dpi, setDpi] = useState<150 | 200 | 300>(300);
  const [padding, setPadding] = useState<0 | 0.05 | 0.1 | 0.2>(0.1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setPage(firstPage); setSelected(null); }, [job.id, firstPage]);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getDocumentTree(job.id, query, controller.signal),
      getQualityReport(job.id, controller.signal),
    ]).then(([items, report]) => { setTree(items); setQuality(report); }).catch(() => undefined);
    return () => controller.abort();
  }, [job.id, job.output_revision, query]);
  useEffect(() => {
    const controller = new AbortController();
    setInspection(null);
    getPageInspection(job.id, page, controller.signal).then((value) => {
      setInspection(value);
      setSelected((current) => current && value.regions.some((region) => region.id === current) ? current : value.regions[0]?.id ?? null);
    }).catch(() => setInspection(null));
    return () => controller.abort();
  }, [job.id, job.output_revision, page]);

  const region = inspection?.regions.find((item) => item.id === selected) ?? null;
  const pages = useMemo(() => job.pages.filter((item) => item.status === "completed"), [job.pages]);

  async function reprocess(target: "page" | "region") {
    if (target === "region" && !region) return;
    setBusy(true); setError(null);
    try {
      await requestReprocess(job.id, { target_kind: target, page_number: page, ...(target === "region" ? { region_id: region!.id } : {}), dpi, crop_padding: padding });
      onJobChanged();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Reprocessing failed"); }
    finally { setBusy(false); }
  }

  function chooseNode(node: DocumentTreeItem) { setPage(node.page); setSelected(node.id); setTab("evidence"); }

  return <section className="document-inspector">
    <aside className="inspector-tree">
      <div className="inspector-head"><strong>Document tree</strong><span>{tree.length} blocks</span></div>
      <label className="tree-search"><Search size={14} /><input aria-label="Search document tree" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search text or type" /></label>
      <div className="page-rail">{pages.map((item) => <button key={item.page_number} className={page === item.page_number ? "active" : ""} onClick={() => setPage(item.page_number)}>P{item.page_number}</button>)}</div>
      <div className="tree-items">{tree.map((item) => <button key={item.id} className={selected === item.id ? "active" : ""} style={{ paddingLeft: `${12 + Math.min(item.heading_path.length, 3) * 9}px` }} onClick={() => chooseNode(item)}><small>P{item.page} · {item.type}</small><span>{item.summary || "Untitled block"}</span></button>)}</div>
    </aside>
    <div className="page-inspector">
      <div className="inspector-head"><strong>Annotated page {page}</strong><a href={apiResourceUrl(job.source_preview_url)} target="_blank" rel="noreferrer">Open source</a></div>
      <div className="page-canvas">{inspection ? <div className="page-image-wrap"><Image unoptimized width={inspection.width} height={inspection.height} src={apiResourceUrl(inspection.image_url)} alt={`Document page ${page}`} />{inspection.regions.map((item) => <button key={item.id} aria-label={`${item.type} ${item.order + 1}`} title={`${item.type} · ${item.source} · ${Math.round((item.confidence ?? 0) * 100)}%`} className={`region-box ${selected === item.id ? "active" : ""} ${item.quality_status === "pass" ? "pass" : "warn"}`} style={{ left: `${item.bbox.x0 / inspection.width * 100}%`, top: `${item.bbox.y0 / inspection.height * 100}%`, width: `${(item.bbox.x1 - item.bbox.x0) / inspection.width * 100}%`, height: `${(item.bbox.y1 - item.bbox.y0) / inspection.height * 100}%` }} onClick={() => setSelected(item.id)}><b>{item.order + 1}</b></button>)}</div> : <div className="inspector-empty"><Loader2 className="spin" /> Page evidence is not available yet.</div>}</div>
      <div className="reprocess-controls"><select aria-label="Reprocess DPI" value={dpi} onChange={(event) => setDpi(Number(event.target.value) as 150 | 200 | 300)}><option value={150}>150 DPI</option><option value={200}>200 DPI</option><option value={300}>300 DPI</option></select><select aria-label="Crop padding" value={padding} onChange={(event) => setPadding(Number(event.target.value) as 0 | 0.05 | 0.1 | 0.2)}><option value={0}>No padding</option><option value={0.05}>5% padding</option><option value={0.1}>10% padding</option><option value={0.2}>20% padding</option></select><button disabled={busy} onClick={() => void reprocess("page")}><RefreshCw size={14} /> Page</button><button disabled={busy || !region} onClick={() => void reprocess("region")}><RefreshCw size={14} /> Region</button></div>
    </div>
    <aside className="evidence-panel">
      <div className="inspector-tabs"><button className={tab === "evidence" ? "active" : ""} onClick={() => setTab("evidence")}>Evidence</button><button className={tab === "markdown" ? "active" : ""} onClick={() => setTab("markdown")}>Markdown</button><button className={tab === "quality" ? "active" : ""} onClick={() => setTab("quality")}>Quality</button></div>
      {error && <div className="inspector-error"><TriangleAlert size={14} />{error}</div>}
      {tab === "evidence" && <div className="evidence-content">{region ? <><div className="region-title"><span>{region.type}</span><strong>{region.id}</strong><small>{region.source_label ?? region.source} · {Math.round((region.confidence ?? 0) * 100)}%</small></div><pre>{region.content}</pre><h3>Recognition candidates</h3>{region.candidates.length ? region.candidates.map((candidate) => <article key={candidate.id} className={candidate.selected ? "candidate selected" : "candidate"}><header><strong>{candidate.source}</strong><span>{candidate.model ?? "local pipeline"}</span>{candidate.selected && <b><Check size={12} /> Selected by agent</b>}</header><pre>{candidate.output}</pre><small>{candidate.verdict} · {candidate.reason}</small></article>) : <p>No alternate recognition candidates were retained.</p>}</> : <p>Select a region to inspect provenance.</p>}</div>}
      {tab === "markdown" && <pre className="inspector-markdown">{region?.markdown || markdown || "Markdown is being assembled."}</pre>}
      {tab === "quality" && <div className="quality-summary">{quality && <><div className="quality-state">{quality.verified_export_ready ? <Check /> : <TriangleAlert />}<div><strong>{quality.verified_export_ready ? "Verified export ready" : "Draft output"}</strong><span>{quality.unresolved_regions.length} unresolved regions</span></div></div><Metric label="OCR coverage" value={quality.ocr_coverage.ratio} /><Metric label="Table integrity" value={quality.table_integrity.ratio} /><Metric label="Agreement" value={quality.ocr_coverage.total_regions ? 1 - quality.disagreements.length / quality.ocr_coverage.total_regions : 1} /><h3>Recognition sources</h3>{Object.entries(quality.source_counts).map(([name, count]) => <p key={name}>{name}<b>{count}</b></p>)}{quality.warnings.map((warning) => <small key={warning}>{warning}</small>)}</>}</div>}
    </aside>
  </section>;
}

function Metric({ label, value }: { label: string; value: number }) { return <div className="quality-line"><span>{label}</span><b>{Math.round(value * 100)}%</b><i><em style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} /></i></div>; }
