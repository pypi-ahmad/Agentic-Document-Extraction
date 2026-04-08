"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  listExtractions,
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
  Clock,
  Loader2,
  ChevronDown,
  ChevronUp,
  Eye,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  Filter,
  Search,
} from "lucide-react";
import FieldTable from "@/components/FieldTable";
import ReviewPanel from "@/components/ReviewPanel";

const STATUS_ICON: Record<string, typeof CheckCircle2> = {
  pending: Clock,
  completed: CheckCircle2,
  needs_review: Eye,
  failed: XCircle,
  queued: Clock,
  processing: Loader2,
  ocr_complete: Loader2,
  extracted: Loader2,
};

const STATUS_COLOR: Record<string, string> = {
  pending: "text-gray-400",
  completed: "text-green-600",
  needs_review: "text-orange-500",
  failed: "text-red-600",
  queued: "text-gray-500",
  processing: "text-blue-500",
  ocr_complete: "text-blue-500",
  extracted: "text-blue-500",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  queued: "Queued",
  processing: "Processing",
  ocr_complete: "Reading",
  extracted: "Extracting",
  completed: "Completed",
  needs_review: "Needs Review",
  failed: "Failed",
};

const IN_PROGRESS_STATUSES = new Set([
  "pending",
  "queued",
  "processing",
  "ocr_complete",
  "extracted",
]);
const TERMINAL_STATUSES = new Set(["completed", "needs_review", "failed"]);

const FILTER_OPTIONS = [
  { value: "all", label: "All" },
  { value: "completed", label: "Completed" },
  { value: "needs_review", label: "Needs Review" },
  { value: "failed", label: "Failed" },
  { value: "in_progress", label: "In Progress" },
] as const;

type FilterValue = (typeof FILTER_OPTIONS)[number]["value"];

export default function HistoryPage() {
  const [extractions, setExtractions] = useState<ExtractionResponse[]>([]);
  const [selected, setSelected] = useState<ExtractionResponse | null>(null);
  const [schema, setSchema] = useState<ExtractionSchemaResponse | null>(null);
  const [showRawJson, setShowRawJson] = useState(false);
  const [statusFilter, setStatusFilter] = useState<FilterValue>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [schemaNames, setSchemaNames] = useState<Record<string, string>>({});
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initial load
  useEffect(() => {
    listExtractions().then(setExtractions).catch(() => {});
  }, []);

  // Poll in-progress extractions every 3 seconds
  useEffect(() => {
    const hasInProgress = extractions.some((e) =>
      IN_PROGRESS_STATUSES.has(e.status),
    );
    if (!hasInProgress) return;

    const tick = async () => {
      const inProgressIds = extractions
        .filter((e) => IN_PROGRESS_STATUSES.has(e.status))
        .map((e) => e.id);

      const updates = await Promise.allSettled(
        inProgressIds.map((id) => getExtraction(id)),
      );

      setExtractions((prev) => {
        const updated = new Map<string, ExtractionResponse>();
        updates.forEach((r) => {
          if (r.status === "fulfilled") updated.set(r.value.id, r.value);
        });
        if (updated.size === 0) return prev;
        return prev.map((e) => updated.get(e.id) ?? e);
      });

      // Also refresh selected if it was in-progress
      if (selected && inProgressIds.includes(selected.id)) {
        const match = updates.find(
          (r) => r.status === "fulfilled" && r.value.id === selected.id,
        );
        if (match && match.status === "fulfilled") setSelected(match.value);
      }
    };

    pollRef.current = setTimeout(tick, 3000);
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [extractions, selected]);

  // Resolve schema names for display
  useEffect(() => {
    const unknownIds = Array.from(
      new Set(
        extractions
          .map((e) => e.schema_id)
          .filter((id) => id && !schemaNames[id]),
      ),
    );
    if (unknownIds.length === 0) return;
    unknownIds.forEach((id) => {
      getSchema(id)
        .then((s) =>
          setSchemaNames((prev) => ({ ...prev, [id]: s.name })),
        )
        .catch(() => {});
    });
  }, [extractions, schemaNames]);

  // Fetch schema when selection changes
  useEffect(() => {
    if (selected) {
      setShowRawJson(false);
      getSchema(selected.schema_id)
        .then(setSchema)
        .catch(() => setSchema(null));
    }
  }, [selected?.id]);

  // Filtered list
  const filtered = useMemo(() => {
    let list = extractions;

    // Status filter
    if (statusFilter === "in_progress") {
      list = list.filter((e) => IN_PROGRESS_STATUSES.has(e.status));
    } else if (statusFilter !== "all") {
      list = list.filter((e) => e.status === statusFilter);
    }

    // Search by schema name or provider
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter((e) => {
        const sName = schemaNames[e.schema_id]?.toLowerCase() ?? "";
        const provider = (e.llm_provider_used ?? e.llm_provider).toLowerCase();
        const reader = (e.ocr_provider_used ?? e.ocr_provider).toLowerCase();
        return sName.includes(q) || provider.includes(q) || reader.includes(q);
      });
    }

    return list;
  }, [extractions, statusFilter, searchQuery, schemaNames]);

  const handleRetried = useCallback(() => {
    listExtractions().then(setExtractions).catch(() => {});
    setSelected(null);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            Extraction History
          </h2>
          <p className="text-sm text-gray-500">
            View past extraction jobs and their results
          </p>
        </div>

        {/* Filter / search bar */}
        {extractions.length > 0 && (
          <div className="flex gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search…"
                className="w-44 rounded-lg border border-gray-300 py-2 pl-8 pr-3 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </div>
            <div className="relative">
              <Filter className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-gray-400" />
              <select
                value={statusFilter}
                onChange={(e) =>
                  setStatusFilter(e.target.value as FilterValue)
                }
                className="appearance-none rounded-lg border border-gray-300 py-2 pl-8 pr-8 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              >
                {FILTER_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>

      {extractions.length === 0 ? (
        <div className="rounded-xl border-2 border-dashed border-gray-200 p-12 text-center">
          <p className="text-gray-500">No extractions yet.</p>
          <p className="mt-1 text-sm text-gray-400">
            <a href="/" className="text-primary-600 hover:underline">
              Upload a document
            </a>{" "}
            and run your first extraction.
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border-2 border-dashed border-gray-200 p-8 text-center">
          <p className="text-gray-500">No matching extractions.</p>
          <button
            type="button"
            onClick={() => {
              setStatusFilter("all");
              setSearchQuery("");
            }}
            className="mt-2 text-sm text-primary-600 hover:underline"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* List */}
          <div className="space-y-2">
            <p className="text-xs text-gray-400">
              {filtered.length} extraction{filtered.length !== 1 ? "s" : ""}
            </p>
            {filtered.map((ext) => {
              const Icon = STATUS_ICON[ext.status] ?? Clock;
              const color = STATUS_COLOR[ext.status] ?? "text-gray-500";
              const isActive = IN_PROGRESS_STATUSES.has(ext.status);
              return (
                <button
                  key={ext.id}
                  type="button"
                  onClick={() => setSelected(ext)}
                  className={`w-full rounded-lg border p-4 text-left transition-colors ${
                    selected?.id === ext.id
                      ? "border-primary-500 bg-primary-50"
                      : "border-gray-200 bg-white hover:bg-gray-50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Icon
                        className={`h-4 w-4 ${color} ${isActive ? "animate-spin" : ""}`}
                      />
                      <span className="text-sm font-medium text-gray-900">
                        {schemaNames[ext.schema_id] ?? "—"}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                          ext.status === "completed"
                            ? "bg-green-100 text-green-700"
                            : ext.status === "needs_review"
                              ? "bg-orange-100 text-orange-700"
                              : ext.status === "failed"
                                ? "bg-red-100 text-red-700"
                                : "bg-blue-100 text-blue-700"
                        }`}
                      >
                        {STATUS_LABEL[ext.status] ?? ext.status}
                      </span>
                    </div>
                    <span className="text-xs text-gray-400" title={new Date(ext.created_at).toLocaleString()}>
                      {timeAgo(ext.created_at)}
                    </span>
                  </div>
                  <div className="mt-1 flex gap-4 text-xs text-gray-500">
                    <span>
                      {new Date(ext.created_at).toLocaleDateString()}
                    </span>
                    <span>
                      Reader:{" "}
                      {resolvedDisplayName(
                        ext.ocr_provider,
                        ext.ocr_provider_used,
                      )}
                    </span>
                    <span>
                      AI:{" "}
                      {resolvedDisplayName(
                        ext.llm_provider,
                        ext.llm_provider_used,
                      )}
                    </span>
                    {ext.duration_total_ms != null && (
                      <span>
                        {ext.duration_total_ms < 1000
                          ? `${ext.duration_total_ms}ms`
                          : `${(ext.duration_total_ms / 1000).toFixed(1)}s`}
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Detail */}
          {selected && (
            <DetailPanel
              extraction={selected}
              schema={schema}
              showRawJson={showRawJson}
              setShowRawJson={setShowRawJson}
              onRetried={handleRetried}
            />
          )}
        </div>
      )}
    </div>
  );
}


// ── Detail Panel ────────────────────────────────────────────────────

function DetailPanel({
  extraction: sel,
  schema,
  showRawJson,
  setShowRawJson,
  onRetried,
}: {
  extraction: ExtractionResponse;
  schema: ExtractionSchemaResponse | null;
  showRawJson: boolean;
  setShowRawJson: (v: boolean) => void;
  onRetried: () => void;
}) {
  const [retrying, setRetrying] = useState(false);
  const needsReview = sel.status === "needs_review";
  const resultData = sel.result as Record<string, unknown> | null;
  const isTerminal = TERMINAL_STATUSES.has(
    sel.status,
  );
  const isInProgress = IN_PROGRESS_STATUSES.has(sel.status);

  return (
    <div className="card space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">
          Extraction Details
        </h3>
        {needsReview && (
          <span className="badge badge-warning flex items-center gap-1">
            <Eye className="h-3 w-3" />
            Review needed
          </span>
        )}
        {sel.status === "completed" && (
          <span className="badge badge-success flex items-center gap-1">
            <ShieldCheck className="h-3 w-3" />
            {sel.review_verdict === "approved"
              ? "Approved by reviewer"
              : sel.review_verdict === "corrected"
                ? "Corrected by reviewer"
                : sel.validation_summary ?? "Completed"}
          </span>
        )}
      </div>

      {/* Step progress */}
      {(isInProgress || isTerminal) && sel.steps && sel.steps.length > 0 && (
        <HistoryStepProgress extraction={sel} />
      )}

      {/* Validation summary */}
      {sel.validation_summary && !needsReview && (
        <p className="text-xs text-gray-500">{sel.validation_summary}</p>
      )}

      {/* Error */}
      {sel.error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3">
          <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" />
          <div className="min-w-0 flex-1">
            {(() => {
              const cat = errorCategoryLabel(sel.error_category);
              return cat ? (
                <span className="mb-1 mr-2 inline-block rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700" title={cat.hint}>
                  {cat.label}
                </span>
              ) : null;
            })()}
            <p className="text-sm text-red-700">{sel.error}</p>
          </div>
        </div>
      )}

      {sel.status === "failed" && (
        <button
          type="button"
          disabled={retrying}
          onClick={async () => {
            setRetrying(true);
            try {
              await retryExtraction(sel.id);
              onRetried();
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

      {/* Validation warnings (non-review states) */}
      {!needsReview &&
        sel.validation_errors &&
        sel.validation_errors.length > 0 && (
          <div className="flex items-start gap-2 rounded-lg bg-yellow-50 p-3">
            <ShieldAlert className="mt-0.5 h-4 w-4 flex-shrink-0 text-yellow-600" />
            <div>
              <p className="text-sm font-medium text-yellow-800">
                Some fields need attention
              </p>
              <ul className="mt-1 list-inside list-disc text-xs text-yellow-700">
                {sel.validation_errors.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

      {/* Human review panel */}
      {needsReview && resultData && (
        <ReviewPanel
          extraction={sel}
          schema={schema}
          onReviewed={onRetried}
        />
      )}

      {/* Structured result (non-review states) */}
      {!needsReview && resultData && (
        <div>
          <h4 className="mb-3 text-sm font-semibold text-gray-700">
            Extracted Data
          </h4>
          <FieldTable
            resultData={resultData}
            schema={schema}
            confidence={sel.confidence}
          />
        </div>
      )}

      {/* Review history */}
      {sel.reviews && sel.reviews.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-500">Review History</h4>
          {sel.reviews.map((r) => (
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

      {isTerminal && !resultData && (
        <p className="text-sm italic text-gray-400">
          No data was extracted from this document.
        </p>
      )}

      {/* Raw JSON toggle */}
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

      {/* Metadata */}
      <div className="border-t border-gray-100 pt-4">
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
          <div>
            <span className="block font-medium text-gray-500">Document reader</span>
            <span className="text-gray-700">
              {resolvedDisplayName(sel.ocr_provider, sel.ocr_provider_used)}
            </span>
          </div>
          <div>
            <span className="block font-medium text-gray-500">AI Provider</span>
            <span className="text-gray-700">
              {resolvedDisplayName(sel.llm_provider, sel.llm_provider_used)}
            </span>
          </div>
          <div>
            <span className="block font-medium text-gray-500">AI Model</span>
            <span className="text-gray-700">
              {sel.llm_model_used ?? sel.llm_model}
            </span>
          </div>
          <div>
            <span className="block font-medium text-gray-500">Completed</span>
            <span className="text-gray-700">
              {sel.completed_at
                ? new Date(sel.completed_at).toLocaleString()
                : "—"}
            </span>
          </div>
          {sel.duration_total_ms != null && (
            <div>
              <span className="block font-medium text-gray-500">Total time</span>
              <span className="text-gray-700">
                {sel.duration_total_ms < 1000
                  ? `${sel.duration_total_ms}ms`
                  : `${(sel.duration_total_ms / 1000).toFixed(1)}s`}
              </span>
            </div>
          )}
          {sel.extract_attempts != null && sel.extract_attempts > 1 && (
            <div>
              <span className="block font-medium text-gray-500">LLM Attempts</span>
              <span className="text-gray-700">{sel.extract_attempts}</span>
            </div>
          )}
          {sel.reviewed_at && (
            <div>
              <span className="block font-medium text-gray-500">Reviewed</span>
              <span
                className="text-gray-700"
                title={new Date(sel.reviewed_at).toLocaleString()}
              >
                {timeAgo(sel.reviewed_at)}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// ── Pipeline step progress (for history detail) ─────────────────────

const PIPELINE_STEPS = [
  { key: "parse", label: "Reading document" },
  { key: "extract", label: "Extracting data" },
  { key: "validate", label: "Validating" },
  { key: "finalize", label: "Finalizing" },
] as const;

function HistoryStepProgress({
  extraction,
}: {
  extraction: ExtractionResponse;
}) {
  const steps = extraction.steps ?? [];
  const stepMap = new Map(steps.map((s) => [s.name, s]));
  const isInProgress = IN_PROGRESS_STATUSES.has(extraction.status);

  return (
    <div className="flex items-center gap-2 text-xs text-gray-400">
      {PIPELINE_STEPS.map(({ key, label }, idx) => {
        const step = stepMap.get(key);
        const done = step?.status === "completed";
        const failed = step?.status === "failed";
        const skipped = step?.status === "skipped";
        const running =
          step?.status === "running" ||
          (!step &&
            !skipped &&
            isInProgress &&
            PIPELINE_STEPS.slice(0, idx).every((s) => stepMap.has(s.key)));

        const durationStr =
          step?.duration_ms != null
            ? `${(step.duration_ms / 1000).toFixed(1)}s`
            : null;

        return (
          <span key={key} className="contents">
            {idx > 0 && <span className="h-px flex-1 bg-gray-200" />}
            <div className="flex flex-col items-center gap-0.5">
              <div
                className={`h-2 w-2 rounded-full ${
                  failed
                    ? "bg-red-500"
                    : done
                      ? "bg-primary-500"
                      : running
                        ? "animate-pulse bg-primary-400"
                        : "bg-gray-300"
                }`}
              />
              <span
                className={
                  done
                    ? "text-gray-600"
                    : running
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
          </span>
        );
      })}
    </div>
  );
}
