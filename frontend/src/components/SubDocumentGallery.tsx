"use client";

import { useEffect, useState } from "react";
import { FileStack, Loader2 } from "lucide-react";

import { listSubdocuments, type ParseJob, type SubDocument } from "../lib/api";
import { ArtifactGallery } from "./ArtifactGallery";

export function SubDocumentGallery({ job }: { job: ParseJob }) {
  const [items, setItems] = useState<SubDocument[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setItems([]);
    setSelected(null);
    setFailed(false);
    if (!job.status.startsWith("completed") || job.segmentation_status !== "completed") return;
    const controller = new AbortController();
    setLoading(true);
    void listSubdocuments(job.id, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setItems(value);
        setSelected(value[0]?.id ?? null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [job.id, job.status, job.segmentation_status]);

  if (job.segmentation_status === "disabled") return null;
  const active = items.find((item) => item.id === selected) ?? null;
  return <section className="subdocument-gallery">
    <div className="subdocument-head"><div><FileStack size={19} /><span><strong>Detected sub-documents</strong><small>Classified page ranges and instance identifiers</small></span></div><b>{job.subdocument_count}</b></div>
    {loading && <div className="subdocument-loading"><Loader2 className="spin" size={18} /> Loading segments…</div>}
    {!loading && items.length > 0 && <div className="subdocument-tabs" role="list" aria-label="Detected sub-documents">{items.map((item) => <button type="button" role="listitem" className={item.id === active?.id ? "active" : ""} key={item.id} onClick={() => setSelected(item.id)}><strong>{item.ordinal}. {item.profile.replaceAll("_", " ")}</strong><small>Pages {item.start_page}–{item.end_page} · {Math.round(item.confidence * 100)}%</small>{item.identifiers[0] && <em>{item.identifiers[0].kind.replaceAll("_", " ")}: {item.identifiers[0].normalized_value}</em>}</button>)}</div>}
    {active && <><div className="subdocument-summary"><span>Source pages <b>{active.start_page}–{active.end_page}</b></span><span>Boundary <b>{Math.round(active.boundary_confidence * 100)}%</b></span><span><b>{active.complete ? "Complete" : "Partial"}</b></span>{active.warnings.map((warning) => <span className="warn" key={warning}>{warning.replaceAll("_", " ")}</span>)}</div><ArtifactGallery jobId={active.id} artifacts={active.artifacts} /></>}
    {!loading && !items.length && <p className="subdocument-empty">{failed ? "Sub-document results could not be loaded." : "No segmentation result is available."}</p>}
  </section>;
}
