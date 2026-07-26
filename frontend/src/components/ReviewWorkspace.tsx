"use client";

import { useEffect, useState } from "react";
import { Check, RefreshCcw, X } from "lucide-react";
import { approveCuratedDocument, decideReviewCase, listReviewCases, type ReviewCase } from "@/lib/api";

export function ReviewWorkspace() {
  const [items, setItems] = useState<ReviewCase[]>([]);
  const [selected, setSelected] = useState<ReviewCase | null>(null);
  const [source, setSource] = useState("");
  const [message, setMessage] = useState("");
  async function refresh() {
    const next = await listReviewCases(); setItems(next);
    const current = next.find((item) => item.id === selected?.id) ?? next[0] ?? null;
    setSelected(current); setSource(current ? JSON.stringify(current.current, null, 2) : "");
  }
  useEffect(() => { void refresh().catch((error) => setMessage(error.message)); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  async function decide(action: "accept" | "correct" | "dismiss") {
    if (!selected) return;
    try {
      const corrected = action === "correct" ? JSON.parse(source) as Record<string, unknown> : undefined;
      await decideReviewCase(selected.id, { expected_revision: selected.revision, action, corrected });
      setMessage(`Review ${action}ed.`); await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Review could not be saved"); }
  }
  return <section className="evaluation-workspace"><div className="evaluation-results">
    <aside><strong>Open review queue</strong>{items.map((item) => <button key={item.id} type="button" className={selected?.id === item.id ? "active" : ""} onClick={() => { setSelected(item); setSource(JSON.stringify(item.current, null, 2)); }}><span>{item.item_key}</span><small>Page {item.page_number ?? "—"} · {item.severity}</small></button>)}{!items.length && <p>No unresolved quality failures.</p>}</aside>
    <div className="evaluation-report">{selected ? <><div className="evaluation-head"><div><span>{selected.item_kind}</span><h2>{selected.item_key}</h2></div><button className="secondary-button" onClick={() => void refresh()}><RefreshCcw size={14} /> Refresh</button></div><p>{selected.failure_codes.join(" · ")}</p><label htmlFor="review-json">Corrected grounded value</label><textarea id="review-json" className="review-json" value={source} onChange={(event) => setSource(event.target.value)} /><div className="staging-actions"><button className="secondary-button" onClick={() => void decide("dismiss")}><X size={14} /> Dismiss</button><button className="secondary-button" onClick={() => void decide("accept")}><Check size={14} /> Accept</button><button className="parse-button" onClick={() => void decide("correct")}>Save correction</button></div><button className="secondary-button" onClick={() => void approveCuratedDocument(selected.job_id).then(() => setMessage("Document approved for dataset export.")).catch((error) => setMessage(error.message))}>Approve document after queue is clear</button></> : <p>Select an unresolved case.</p>}{message && <p className="schema-message">{message}</p>}</div>
  </div></section>;
}
