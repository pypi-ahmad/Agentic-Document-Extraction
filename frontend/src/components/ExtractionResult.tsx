"use client";

import { useEffect, useState } from "react";
import {
  getExtraction,
  getSchema,
  retryExtraction,
  displayName,
  resolvedDisplayName,
  errorCategoryLabel,
  timeAgo,
  type ExtractionResponse,
  type ExtractionSchemaResponse,
} from "@/lib/api";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  ChevronDown,
  ChevronUp,
  Eye,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
} from "lucide-react";
import FieldTable from "./FieldTable";
import ReviewPanel from "./ReviewPanel";

interface ExtractionResultProps {
  extractionId: string;
}

const STATUS_CONFIG: Record<
  string,
  { icon: typeof CheckCircle2; color: string; label: string }
> = {
  pending: { icon: Clock, color: "text-gray-400", label: "Starting…" },
  queued: { icon: Clock, color: "text-gray-500", label: "Starting…" },
  processing: {
    icon: Loader2,
    color: "text-blue-500",
    label: "Reading document…",
  },
  ocr_complete: {
    icon: Loader2,
    color: "text-blue-500",
    label: "Extracting data…",
  },
  extracted: {
    icon: Loader2,
    color: "text-blue-500",
    label: "Validating…",
  },
  completed: {
    icon: CheckCircle2,
    color: "text-green-600",
    label: "Completed",
  },
  needs_review: {
    icon: Eye,
    color: "text-orange-500",
    label: "Review recommended",
  },
  failed: { icon: XCircle, color: "text-red-600", label: "Failed" },
};

const IN_PROGRESS = [
  "pending",
  "queued",
  "processing",
  "ocr_complete",
  "extracted",
];

const TERMINAL = ["completed", "needs_review", "failed"];


// ── Main component ──────────────────────────────────────────────────

export default function ExtractionResult({
  extractionId,
}: ExtractionResultProps) {
  const [extraction, setExtraction] = useState<ExtractionResponse | null>(
    null,
  );
  const [schema, setSchema] = useState<ExtractionSchemaResponse | null>(null);
  const [showRawJson, setShowRawJson] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [pollKey, setPollKey] = useState(0);

  // Stream extraction status via SSE, fall back to polling
  useEffect(() => {
    let active = true;
    let eventSource: EventSource | null = null;

    const startSSE = () => {
      eventSource = new EventSource(`/api/extractions/${extractionId}/stream`);

      eventSource.onmessage = (event) => {
        if (!active) return;
        try {
          const data = JSON.parse(event.data) as ExtractionResponse;
          if (data.error && !data.status) {
            // SSE reported extraction not found — stop
            eventSource?.close();
            return;
          }
          setExtraction(data);
          if (TERMINAL.includes(data.status)) {
            eventSource?.close();
          }
        } catch {
          // ignore parse errors
        }
      };

      eventSource.onerror = () => {
        eventSource?.close();
        // Fall back to one-shot poll after SSE disconnects
        if (active) fallbackPoll();
      };
    };

    const fallbackPoll = async () => {
      try {
        const data = await getExtraction(extractionId);
        if (!active) return;
        setExtraction(data);
        if (IN_PROGRESS.includes(data.status)) {
          setTimeout(fallbackPoll, 2000);
        }
      } catch {
        if (active) setTimeout(fallbackPoll, 3000);
      }
    };

    startSSE();

    return () => {
      active = false;
      eventSource?.close();
    };
  }, [extractionId, pollKey]);

  // Fetch schema once extraction is loaded
  useEffect(() => {
    if (extraction?.schema_id && !schema) {
      getSchema(extraction.schema_id).catch(() => null).then((s) => {
        if (s) setSchema(s);
      });
    }
  }, [extraction?.schema_id, schema]);

  // Loading state
  if (!extraction) {
    return (
      <div className="card flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  const config = STATUS_CONFIG[extraction.status] ?? STATUS_CONFIG.processing;
  const StatusIcon = config.icon;
  const isInProgress = IN_PROGRESS.includes(extraction.status);
  const isTerminal = TERMINAL.includes(
    extraction.status,
  );
  const needsReview = extraction.status === "needs_review";

  const resultData = extraction.result as Record<string, unknown> | null;

  return (
    <div className="card space-y-5">
      {/* ── Status header ──────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <StatusIcon
            className={`h-5 w-5 ${config.color} ${isInProgress ? "animate-spin" : ""}`}
          />
          <span className={`text-sm font-semibold ${config.color}`}>
            {config.label}
          </span>
        </div>
        {needsReview && (
          <span className="badge badge-warning flex items-center gap-1">
            <Eye className="h-3 w-3" />
            Review needed
          </span>
        )}
        {extraction.status === "completed" && (
          <span className="badge badge-success flex items-center gap-1">
            <ShieldCheck className="h-3 w-3" />
            {extraction.review_verdict === "approved"
              ? "Approved by reviewer"
              : extraction.review_verdict === "corrected"
                ? "Corrected by reviewer"
                : extraction.validation_summary ?? "Completed"}
          </span>
        )}
      </div>

      {/* ── Progress steps ─────────────────────────────────────── */}
      {(isInProgress || isTerminal) && (
        <StepProgress extraction={extraction} />
      )}

      {/* ── Validation summary ─────────────────────────────────── */}
      {extraction.validation_summary && !needsReview && (
        <p className="text-xs text-gray-500">{extraction.validation_summary}</p>
      )}

      {/* ── Validation warnings (non-review states) ──────────── */}
      {!needsReview &&
        extraction.validation_errors &&
        extraction.validation_errors.length > 0 && (
          <div className="flex items-start gap-2 rounded-lg bg-yellow-50 p-3">
            <ShieldAlert className="mt-0.5 h-4 w-4 flex-shrink-0 text-yellow-600" />
            <div>
              <p className="text-sm font-medium text-yellow-800">
                Some fields need attention
              </p>
              <ul className="mt-1 list-inside list-disc text-xs text-yellow-700">
                {extraction.validation_errors.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

      {/* ── Error ──────────────────────────────────────────────── */}
      {extraction.error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3">
          <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" />
          <div className="min-w-0 flex-1">
            {(() => {
              const cat = errorCategoryLabel(extraction.error_category);
              return cat ? (
                <span className="mb-1 mr-2 inline-block rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700" title={cat.hint}>
                  {cat.label}
                </span>
              ) : null;
            })()}
            <p className="text-sm text-red-700">{extraction.error}</p>
          </div>
        </div>
      )}

      {extraction.status === "failed" && (
        <button
          type="button"
          disabled={retrying}
          onClick={async () => {
            setRetrying(true);
            try {
              await retryExtraction(extractionId);
              setPollKey((k) => k + 1);
            } finally {
              setRetrying(false);
            }
          }}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw className={`h-4 w-4 ${retrying ? "animate-spin" : ""}`} />
          {retrying ? "Retrying…" : "Retry extraction"}
        </button>
      )}

      {/* ── Human review panel ─────────────────────────────────── */}
      {needsReview && resultData && (
        <ReviewPanel
          extraction={extraction}
          schema={schema}
          onReviewed={() => setPollKey((k) => k + 1)}
        />
      )}

      {/* ── Extracted data (completed / non-review) ────────────── */}
      {!needsReview && resultData && (
        <div>
          <h4 className="mb-3 text-sm font-semibold text-gray-700">
            Extracted Data
          </h4>
          <FieldTable
            resultData={resultData}
            schema={schema}
            confidence={extraction.confidence}
          />
        </div>
      )}

      {isTerminal && !resultData && (
        <p className="text-sm italic text-gray-400">
          No data was extracted from this document.
        </p>
      )}

      {/* ── Review history ─────────────────────────────────────── */}
      {extraction.reviews && extraction.reviews.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-500">Review History</h4>
          {extraction.reviews.map((r) => (
            <div
              key={r.id}
              className="flex items-start gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-xs"
            >
              <span
                className={`inline-block rounded px-1.5 py-0.5 font-medium ${
                  r.decision === "approved"
                    ? "bg-green-100 text-green-700"
                    : r.decision === "corrected"
                      ? "bg-orange-100 text-orange-700"
                      : "bg-red-100 text-red-700"
                }`}
              >
                {r.decision}
              </span>
              {r.notes && (
                <span className="text-gray-600">{r.notes}</span>
              )}
              <span className="ml-auto whitespace-nowrap text-gray-400">
                {new Date(r.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ── Raw JSON toggle ────────────────────────────────────── */}
      {resultData && (
        <div>
          <button
            type="button"
            onClick={() => setShowRawJson(!showRawJson)}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600"
          >
            {showRawJson ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
            Raw JSON
          </button>
          {showRawJson && (
            <div className="mt-2 overflow-auto rounded-lg bg-gray-900 p-4">
              <pre className="text-xs text-green-400">
                {JSON.stringify(resultData, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* ── Job details ────────────────────────────────────────── */}
      {isTerminal && (
        <div className="border-t border-gray-100 pt-4">
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
            <div>
              <span className="block font-medium text-gray-500">Document reader</span>
              <span className="text-gray-700">
                {resolvedDisplayName(extraction.ocr_provider, extraction.ocr_provider_used)}
              </span>
            </div>
            <div>
              <span className="block font-medium text-gray-500">
                AI Provider
              </span>
              <span className="text-gray-700">
                {resolvedDisplayName(extraction.llm_provider, extraction.llm_provider_used)}
              </span>
            </div>
            <div>
              <span className="block font-medium text-gray-500">AI Model</span>
              <span className="text-gray-700">
                {extraction.llm_model_used ?? extraction.llm_model}
              </span>
            </div>
            <div>
              <span className="block font-medium text-gray-500">
                Completed
              </span>
              <span className="text-gray-700">
                {extraction.completed_at
                  ? new Date(extraction.completed_at).toLocaleString()
                  : "—"}
              </span>
            </div>
            {extraction.duration_total_ms != null && (
              <div>
                <span className="block font-medium text-gray-500">Total time</span>
                <span className="text-gray-700">
                  {extraction.duration_total_ms < 1000
                    ? `${extraction.duration_total_ms}ms`
                    : `${(extraction.duration_total_ms / 1000).toFixed(1)}s`}
                </span>
              </div>
            )}
            {extraction.extract_attempts != null && extraction.extract_attempts > 1 && (
              <div>
                <span className="block font-medium text-gray-500">
                  LLM Attempts
                </span>
                <span className="text-gray-700">
                  {extraction.extract_attempts}
                </span>
              </div>
            )}
            {extraction.reviewed_at && (
              <div>
                <span className="block font-medium text-gray-500">
                  Reviewed
                </span>
                <span className="text-gray-700" title={new Date(extraction.reviewed_at).toLocaleString()}>
                  {timeAgo(extraction.reviewed_at)}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Pipeline step progress ──────────────────────────────────────────

const PIPELINE_STEPS = [
  { key: "parse", label: "Reading document" },
  { key: "extract", label: "Extracting data" },
  { key: "validate", label: "Validating" },
  { key: "finalize", label: "Finalizing" },
] as const;

function StepProgress({ extraction }: { extraction: ExtractionResponse }) {
  const steps = extraction.steps ?? [];
  const stepMap = new Map(steps.map((s) => [s.name, s]));
  const isInProgress = IN_PROGRESS.includes(extraction.status);

  return (
    <div className="flex items-center gap-2 text-xs text-gray-400">
      {PIPELINE_STEPS.map(({ key, label }, idx) => {
        const step = stepMap.get(key);
        const done = step?.status === "completed";
        const failed = step?.status === "failed";
        const skipped = step?.status === "skipped";

        // Running = explicit "running" status OR inferred from absence
        const running =
          step?.status === "running" ||
          (!step &&
            !skipped &&
            isInProgress &&
            PIPELINE_STEPS.slice(0, idx).every((s) => stepMap.has(s.key)));

        return (
          <span key={key} className="contents">
            {idx > 0 && <span className="h-px flex-1 bg-gray-200" />}
            <StepDot
              done={done}
              failed={failed}
              active={running}
              label={label}
              durationMs={step?.duration_ms}
            />
          </span>
        );
      })}
    </div>
  );
}

function StepDot({
  done,
  failed,
  active,
  label,
  durationMs,
}: {
  done: boolean;
  failed?: boolean;
  active: boolean;
  label: string;
  durationMs?: number | null;
}) {
  const durationStr =
    durationMs != null ? `${(durationMs / 1000).toFixed(1)}s` : null;

  return (
    <div className="flex flex-col items-center gap-0.5">
      <div
        className={`h-2 w-2 rounded-full ${
          failed
            ? "bg-red-500"
            : done
              ? "bg-primary-500"
              : active
                ? "animate-pulse bg-primary-400"
                : "bg-gray-300"
        }`}
      />
      <span
        className={
          done
            ? "text-gray-600"
            : active
              ? "text-gray-600"
              : failed
                ? "text-red-500"
                : "text-gray-400"
        }
      >
        {label}
      </span>
      {durationStr && (
        <span className="text-[10px] text-gray-400">{durationStr}</span>
      )}
    </div>
  );
}
