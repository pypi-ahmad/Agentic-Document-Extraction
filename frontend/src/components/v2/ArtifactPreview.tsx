"use client";

import { Download, FileArchive, FileCode2, FileText, LoaderCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { apiResourceUrl, artifactUrl, type AgentTraceEvent, type AgenticParseArtifact, type ParseReview } from "@/lib/api";

const NAMES: Record<string, string> = {
  markdown: "Markdown",
  json: "JSON",
  annotated_pdf: "Annotated PDF",
};

function name(artifact: AgenticParseArtifact) {
  return NAMES[artifact.type] ?? artifact.type.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isText(artifact: AgenticParseArtifact) {
  return artifact.mime_type.startsWith("text/") || artifact.mime_type === "application/json";
}

type ResultTab = "annotated_pdf" | "markdown" | "json" | "extract" | "review" | "trace";

const TAB_LABELS: Record<ResultTab, string> = {
  annotated_pdf: "Annotated PDF",
  markdown: "Markdown",
  json: "JSON",
  extract: "Extract",
  review: "Review",
  trace: "Agent Trace",
};

function artifactFor(tab: ResultTab, artifacts: AgenticParseArtifact[]) {
  if (tab === "extract") return artifacts.find((artifact) => artifact.type === "extract" || artifact.type === "extraction") ?? null;
  if (tab === "review" || tab === "trace") return null;
  return artifacts.find((artifact) => artifact.type === tab) ?? null;
}

export function ArtifactPreview({ jobId, artifacts, reviews, trace }: { jobId: string; artifacts: AgenticParseArtifact[]; reviews: ParseReview[]; trace: AgentTraceEvent[] }) {
  const [selectedTab, setSelectedTab] = useState<ResultTab>("annotated_pdf");
  const [content, setContent] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");

  useEffect(() => setSelectedTab("annotated_pdf"), [jobId]);

  const selected = useMemo(() => artifactFor(selectedTab, artifacts), [artifacts, selectedTab]);

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

  if (!artifacts.length && !reviews.length && !trace.length) {
    return <div className="artifact-preview-empty"><FileArchive size={25} /><span>Grounded outputs appear when extraction completes.</span></div>;
  }

  return (
    <div className="artifact-workspace">
      <div className="artifact-tabs" aria-label="Generated artifacts">
        {(Object.keys(TAB_LABELS) as ResultTab[]).map((tab) => {
          const artifact = artifactFor(tab, artifacts);
          return <div className={selectedTab === tab ? "selected" : ""} key={tab}>
            <button type="button" aria-pressed={selectedTab === tab} onClick={() => setSelectedTab(tab)}>
              {artifact?.mime_type === "application/json" ? <FileCode2 size={14} /> : <FileText size={14} />}
              {TAB_LABELS[tab]}
            </button>
            {artifact && <a href={artifactUrl(artifact)} download aria-label={`Download ${name(artifact)}`} title={`Download ${name(artifact)}`}><Download size={14} /></a>}
          </div>;
        })}
      </div>
      <div className="artifact-content" aria-live="polite">
        {selectedTab === "review" && <ReviewList reviews={reviews} />}
        {selectedTab === "trace" && <TraceList trace={trace} />}
        {selectedTab === "extract" && !selected && <div className="artifact-message">No structured extraction was requested for this parse.</div>}
        {selected?.mime_type === "application/pdf" && selected.preview_url && (
          <iframe title={`${name(selected)} preview`} src={apiResourceUrl(selected.preview_url)} sandbox="" />
        )}
        {state === "loading" && <div className="artifact-message"><LoaderCircle className="spin" size={20} /> Loading preview…</div>}
        {state === "ready" && <pre>{content}</pre>}
        {state === "error" && <div className="artifact-message">Preview unavailable. Download the artifact to inspect it.</div>}
        {state === "idle" && selected && !isText(selected) && !selected.preview_url && <div className="artifact-message"><FileArchive size={24} />This artifact is download-only.</div>}
        {state === "idle" && !selected && selectedTab !== "review" && selectedTab !== "trace" && selectedTab !== "extract" && <div className="artifact-message">This output is not available yet.</div>}
      </div>
    </div>
  );
}

function ReviewList({ reviews }: { reviews: ParseReview[] }) {
  if (!reviews.length) return <div className="artifact-message">No review cases need attention.</div>;
  return <div className="artifact-message">{reviews.map((review) => <p key={review.id}><strong>{review.severity}</strong>{review.page_number ? ` · page ${review.page_number}` : ""} — {review.summary}</p>)}</div>;
}

function TraceList({ trace }: { trace: AgentTraceEvent[] }) {
  if (!trace.length) return <div className="artifact-message">Agent actions will appear while parsing runs.</div>;
  return <div className="artifact-message">{trace.map((event, index) => <p key={`${event.agent}-${event.action}-${index}`}><strong>{event.agent}</strong> · {event.action}{event.page_number ? ` · page ${event.page_number}` : ""}<br /><span>{event.summary}</span></p>)}</div>;
}
