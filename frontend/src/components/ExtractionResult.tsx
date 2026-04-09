"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  getExtraction,
  getSchema,
  retryExtraction,
  resolvedModelDisplayName,
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
    label: "Needs review",
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
const ACTIVE_PIPELINE_STATUSES = ["processing", "ocr_complete", "extracted"];


// ── Main component ──────────────────────────────────────────────────

export default function ExtractionResult({
  extractionId,
}: ExtractionResultProps) {
  const [extraction, setExtraction] = useState<ExtractionResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [schema, setSchema] = useState<ExtractionSchemaResponse | null>(null);
  const [showRawJson, setShowRawJson] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [pollKey, setPollKey] = useState(0);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const lastStatusRef = useRef<string | null>(null);

  // Stream extraction status via SSE, fall back to polling
  useEffect(() => {
    let active = true;

    const clearPoll = () => {
      if (pollRef.current) {
        clearTimeout(pollRef.current);
        pollRef.current = null;
      }
    };

    const closeStream = () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };

    const applyExtraction = (data: ExtractionResponse) => {
      lastStatusRef.current = data.status;
      setExtraction(data);
      setLoading(false);
      setLoadError(null);
      setRefreshError(null);
      setActionError(null);
    };

    const schedulePoll = (delayMs: number, task: () => void) => {
      clearPoll();
      pollRef.current = setTimeout(task, delayMs);
    };

    const fallbackPoll = (delayMs = 0) => {
      schedulePoll(delayMs, async () => {
        try {
          const data = await getExtraction(extractionId);
          if (!active) return;
          applyExtraction(data);
          if (IN_PROGRESS.includes(data.status)) {
            fallbackPoll(2000);
          }
        } catch (err) {
          if (!active) return;
          if (err instanceof ApiError && err.status === 404) {
            setExtraction(null);
            lastStatusRef.current = null;
            setLoading(false);
            setRefreshError(null);
            setLoadError(err.message);
            return;
          }

          setLoading(false);
          if (lastStatusRef.current) {
            setRefreshError(
              "Live updates paused. Showing the last known status while retrying.",
            );
            fallbackPoll(3000);
          } else {
            setLoadError(
              err instanceof Error
                ? err.message
                : "Could not load extraction status.",
            );
          }
        }
      });
    };

    const startSSE = () => {
      closeStream();
      eventSourceRef.current = new EventSource(
        `/api/extractions/${extractionId}/stream`,
      );

      eventSourceRef.current.onmessage = (event) => {
        if (!active) return;
        try {
          const data = JSON.parse(event.data) as
            | ExtractionResponse
            | { error?: string; status?: string };
          if (data.error && !data.status) {
            closeStream();
            clearPoll();
            setExtraction(null);
            lastStatusRef.current = null;
            setLoading(false);
            setRefreshError(null);
            setLoadError(data.error);
            return;
          }

          applyExtraction(data as ExtractionResponse);
          if (data.status && TERMINAL.includes(data.status)) {
            closeStream();
          }
        } catch {
          // ignore parse errors
        }
      };

      eventSourceRef.current.onerror = () => {
        closeStream();
        if (!active) return;
        if (lastStatusRef.current && TERMINAL.includes(lastStatusRef.current)) {
          return;
        }
        setRefreshError("Live stream disconnected. Switching to polling.");
        fallbackPoll(0);
      };
    };

    const loadSnapshot = async () => {
      setLoading(true);
      setLoadError(null);
      setRefreshError(null);
      clearPoll();
      closeStream();

      try {
        const data = await getExtraction(extractionId);
        if (!active) return;
        applyExtraction(data);
        if (IN_PROGRESS.includes(data.status)) {
          startSSE();
        }
      } catch (err) {
        if (!active) return;
        setExtraction(null);
        lastStatusRef.current = null;
        setLoading(false);
        setLoadError(
          err instanceof Error
            ? err.message
            : "Could not load extraction status.",
        );
      }
    };

    void loadSnapshot();

    return () => {
      active = false;
      clearPoll();
      closeStream();
    };
  }, [extractionId, pollKey]);

  // Fetch schema once extraction is loaded
  useEffect(() => {
    if (!extraction?.schema_id) {
      setSchema(null);
      return;
    }

    if (schema?.id === extraction.schema_id) {
      return;
    }

    setSchema(null);
    getSchema(extraction.schema_id)
      .then(setSchema)
      .catch(() => setSchema(null));
  }, [extraction?.schema_id, schema?.id]);

  // Loading state
  if (loading) {
    return (
      <div className="card flex flex-col items-center justify-center gap-2 py-8 text-center">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        <p className="text-sm text-gray-500">Loading extraction status…</p>
      </div>
    );
  }

  if (loadError && !extraction) {
    return (
      <div className="card space-y-4">
        <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3">
          <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-red-700">Could not load extraction status.</p>
            <p className="text-sm text-red-600">{loadError}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setPollKey((k) => k + 1)}
          className="btn-secondary inline-flex items-center gap-2"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      </div>
    );
  }

  if (!extraction) {
    return null;
  }

  const config = STATUS_CONFIG[extraction.status] ?? STATUS_CONFIG.processing;
  const StatusIcon = config.icon;
  const isInProgress = IN_PROGRESS.includes(extraction.status);
  const isTerminal = TERMINAL.includes(
    extraction.status,
  );
  const needsReview = extraction.status === "needs_review";
  const wasRejected = extraction.review_verdict === "rejected";
  const headerLabel = wasRejected ? "Rejected by reviewer" : config.label;
  const errorLabel = wasRejected
    ? {
        label: "Rejected by reviewer",
        hint: "A reviewer marked this extraction as unusable.",
      }
    : errorCategoryLabel(extraction.error_category);

  const resultData = extraction.result as Record<string, unknown> | null;

  return (
    <div className="card space-y-5">
      {refreshError && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {refreshError}
        </div>
      )}

      {actionError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {actionError}
        </div>
      )}

      {/* ── Status header ──────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <StatusIcon
            className={`h-5 w-5 ${config.color} ${isInProgress ? "animate-spin" : ""}`}
          />
          <span className={`text-sm font-semibold ${config.color}`}>
            {headerLabel}
          </span>
        </div>
        {needsReview && (
          <span className="badge badge-warning flex items-center gap-1">
            <Eye className="h-3 w-3" />
            Needs review
          </span>
        )}
        {wasRejected && (
          <span className="badge badge-error flex items-center gap-1">
            <XCircle className="h-3 w-3" />
            Rejected by reviewer
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
      {(isInProgress || isTerminal) && extraction.steps.length > 0 && (
        <StepProgress extraction={extraction} />
      )}

      {/* ── Validation summary ─────────────────────────────────── */}
      {extraction.validation_summary && !needsReview && (
        <p className="text-xs text-gray-500">{extraction.validation_summary}</p>
      )}

      {/* ── Validation warnings (non-review states) ──────────── */}
      {!needsReview &&
        !extraction.review_verdict &&
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
            {errorLabel ? (
              <span className="mb-1 mr-2 inline-block rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700" title={errorLabel.hint}>
                {errorLabel.label}
              </span>
            ) : null}
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
            setActionError(null);
            try {
              const retried = await retryExtraction(extractionId);
              lastStatusRef.current = retried.status;
              setExtraction(retried);
              setLoadError(null);
              setRefreshError(null);
              setPollKey((k) => k + 1);
            } catch (err) {
              setActionError(
                err instanceof Error
                  ? err.message
                  : "Could not retry extraction.",
              );
            } finally {
              setRetrying(false);
            }
          }}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw className={`h-4 w-4 ${retrying ? "animate-spin" : ""}`} />
          {retrying
            ? wasRejected
              ? "Restarting…"
              : "Retrying…"
            : wasRejected
              ? "Run extraction again"
              : "Retry extraction"}
        </button>
      )}

      {/* ── Human review panel ─────────────────────────────────── */}
      {needsReview && resultData && (
        <ReviewPanel
          extraction={extraction}
          schema={schema}
          onReviewed={() => {
            setActionError(null);
            setPollKey((k) => k + 1);
          }}
        />
      )}

      {/* ── Extracted data (completed / non-review) ────────────── */}
      {!needsReview && resultData && extraction.review_verdict !== "rejected" && (
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
                {r.decision.charAt(0).toUpperCase() + r.decision.slice(1)}
              </span>
              <div className="min-w-0 flex-1 space-y-1">
                {r.corrected_fields && Object.keys(r.corrected_fields).length > 0 && (
                  <div className="text-gray-600">
                    Updated: {Object.keys(r.corrected_fields).join(", ")}
                  </div>
                )}
                {r.notes && (
                  <div className="text-gray-600">{r.notes}</div>
                )}
              </div>
              <span className="ml-auto whitespace-nowrap text-gray-400">
                {new Date(r.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ── Raw JSON toggle ────────────────────────────────────── */}
      {resultData && extraction.review_verdict !== "rejected" && (
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
            {showRawJson ? "Hide advanced debug JSON" : "Show advanced debug JSON"}
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
                {resolvedModelDisplayName(
                  extraction.llm_model,
                  extraction.llm_model_used,
                )}
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
  const canInferRunning = ACTIVE_PIPELINE_STATUSES.includes(extraction.status);

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
            canInferRunning &&
            PIPELINE_STEPS.slice(0, idx).every((s) => stepMap.has(s.key)));

        return (
          <span key={key} className="contents">
            {idx > 0 && <span className="h-px flex-1 bg-gray-200" />}
            <StepDot
              done={done}
              failed={failed}
              skipped={skipped}
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
  skipped,
  active,
  label,
  durationMs,
}: {
  done: boolean;
  failed?: boolean;
  skipped?: boolean;
  active: boolean;
  label: string;
  durationMs?: number | null;
}) {
  const durationStr =
    durationMs != null ? `${(durationMs / 1000).toFixed(1)}s` : null;
  const statusTitle = failed
    ? `${label}: failed`
    : skipped
      ? `${label}: skipped`
      : active
        ? `${label}: running`
        : done
          ? `${label}: completed`
          : label;

  return (
    <div className="flex flex-col items-center gap-0.5" title={statusTitle}>
      <div
        className={`h-2 w-2 rounded-full ${
          failed
            ? "bg-red-500"
            : done
              ? "bg-primary-500"
              : skipped
                ? "border border-gray-400 bg-white"
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
                : skipped
                  ? "text-gray-500"
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
