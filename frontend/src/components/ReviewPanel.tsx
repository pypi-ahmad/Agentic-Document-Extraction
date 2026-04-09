"use client";

import { useState } from "react";
import {
  submitReview,
  type ExtractionResponse,
  type ExtractionSchemaResponse,
  type ReviewDecision,
} from "@/lib/api";
import {
  CheckCircle2,
  XCircle,
  Pencil,
  ShieldCheck,
  ShieldAlert,
  Loader2,
} from "lucide-react";

interface ReviewPanelProps {
  extraction: ExtractionResponse;
  schema: ExtractionSchemaResponse | null;
  onReviewed: () => void;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) return JSON.stringify(value, null, 2);
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function isStructuredValue(value: unknown): boolean {
  return Array.isArray(value) || (typeof value === "object" && value !== null);
}

export default function ReviewPanel({
  extraction,
  schema,
  onReviewed,
}: ReviewPanelProps) {
  const resultData = (extraction.result ?? {}) as Record<string, unknown>;
  const validationResults = extraction.validation_results ?? [];

  // Build a map of field → validation outcome
  const fieldValidation = new Map<
    string,
    { valid: boolean; message: string }
  >();
  for (const vr of validationResults) {
    if (vr.field_name) {
      fieldValidation.set(vr.field_name, {
        valid: vr.valid,
        message: vr.message,
      });
    }
  }

  const fieldKeys: string[] = schema
    ? schema.fields.map((f) => f.name)
    : Object.keys(resultData);

  const schemaFieldMap = new Map(
    (schema?.fields ?? []).map((f) => [f.name, f]),
  );

  // Track which fields are being edited and their corrected values
  const [editingFields, setEditingFields] = useState<Set<string>>(new Set());
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState<ReviewDecision | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasCorrections = Object.keys(corrections).length > 0;

  const toggleEdit = (key: string) => {
    const next = new Set(editingFields);
    if (next.has(key)) {
      next.delete(key);
      const nextCorrections = { ...corrections };
      delete nextCorrections[key];
      setCorrections(nextCorrections);
    } else {
      next.add(key);
      // Initialize with current value
      setCorrections({
        ...corrections,
        [key]: formatValue(resultData[key]),
      });
    }
    setEditingFields(next);
  };

  const handleSubmit = async (decision: ReviewDecision) => {
    setSubmitting(decision);
    setError(null);
    try {
      // Parse corrected field values back to appropriate types
      let correctedFields: Record<string, unknown> | undefined;
      if (decision === "corrected" && hasCorrections) {
        correctedFields = {};
        for (const [key, rawVal] of Object.entries(corrections)) {
          const schemaDef = schemaFieldMap.get(key);
          correctedFields[key] = parseFieldValue(rawVal, schemaDef?.field_type);
        }
      }

      await submitReview(extraction.id, {
        decision,
        corrected_fields: correctedFields ?? null,
        notes: notes.trim() || null,
      });
      onReviewed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed");
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="space-y-4 rounded-lg border-2 border-orange-200 bg-orange-50/50 p-4">
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-5 w-5 text-orange-600" />
        <h4 className="text-sm font-semibold text-orange-800">
          Human Review Required
        </h4>
      </div>
      <p className="text-sm text-orange-800">
        The extraction finished, but one or more fields need confirmation before you rely on this result.
      </p>
      <p className="text-xs text-orange-700">
        Approve keeps the current values, Save corrections updates only the fields you edit, and Reject marks this run as unusable so it can be rerun.
      </p>

      {extraction.validation_errors && extraction.validation_errors.length > 0 && (
        <div className="rounded-lg border border-orange-200 bg-orange-100/70 px-3 py-2 text-sm text-orange-900">
          <p className="font-medium">Why this needs review</p>
          <ul className="mt-1 list-inside list-disc text-xs text-orange-800">
            {extraction.validation_errors.map((warning, index) => (
              <li key={`${warning}-${index}`}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Per-field review table */}
      <div className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
        {fieldKeys.map((key) => {
          const value = resultData[key];
          const schemaDef = schemaFieldMap.get(key);
          const validation = fieldValidation.get(key);
          const isValid = validation?.valid ?? true;
          const isEditing = editingFields.has(key);

          return (
            <div key={key} className="px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-start gap-2">
                    {isValid ? (
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-green-500" />
                    ) : (
                      <XCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-red-500" />
                    )}
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-800">
                        {schemaDef?.description || key}
                      </div>
                      {schemaDef?.description && schemaDef.description !== key && (
                        <div className="text-xs text-gray-400">{key}</div>
                      )}
                    </div>
                    {!isValid && validation?.message && (
                      <span className="text-xs text-red-600">
                        — {validation.message}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {isEditing ? (
                    schemaDef?.field_type === "list" || schemaDef?.field_type === "object" ? (
                      <textarea
                        value={corrections[key] ?? ""}
                        onChange={(e) =>
                          setCorrections({
                            ...corrections,
                            [key]: e.target.value,
                          })
                        }
                        rows={3}
                        className="min-w-[16rem] rounded border border-orange-300 px-2 py-1 font-mono text-xs focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                      />
                    ) : (
                      <input
                        type="text"
                        value={corrections[key] ?? ""}
                        onChange={(e) =>
                          setCorrections({
                            ...corrections,
                            [key]: e.target.value,
                          })
                        }
                        className="rounded border border-orange-300 px-2 py-1 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                      />
                    )
                  ) : (
                    isStructuredValue(value) ? (
                      <pre
                        className={`max-w-md whitespace-pre-wrap break-words rounded bg-gray-50 px-2 py-1 text-left font-mono text-xs ${
                          value === null || value === undefined
                            ? "italic text-gray-400"
                            : "text-gray-800"
                        }`}
                      >
                        {formatValue(value) || "—"}
                      </pre>
                    ) : (
                      <span
                        className={`text-sm ${
                          value === null || value === undefined
                            ? "italic text-gray-400"
                            : "text-gray-900"
                        }`}
                      >
                        {formatValue(value) || "—"}
                      </span>
                    )
                  )}
                  <button
                    type="button"
                    onClick={() => toggleEdit(key)}
                    className={`rounded p-1 transition-colors ${
                      isEditing
                        ? "bg-orange-100 text-orange-700"
                        : "text-gray-400 hover:text-gray-600"
                    }`}
                    title={isEditing ? "Cancel edit" : "Edit value"}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Reviewer notes */}
      <div>
        <label
          htmlFor="review-notes"
          className="mb-1 block text-xs font-medium text-gray-600"
        >
          Notes (optional)
        </label>
        <textarea
          id="review-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Explain corrections or reasons for approval/rejection…"
          rows={2}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
        />
      </div>

      {error && (
        <p className="text-sm text-red-600">{error}</p>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={submitting !== null}
          onClick={() => handleSubmit("approved")}
          className="btn-primary flex items-center gap-1.5"
        >
          {submitting === "approved" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ShieldCheck className="h-4 w-4" />
          )}
          Approve as-is
        </button>

        {hasCorrections && (
          <button
            type="button"
            disabled={submitting !== null}
            onClick={() => handleSubmit("corrected")}
            className="btn-secondary flex items-center gap-1.5 border-orange-300 bg-orange-50 text-orange-700 hover:bg-orange-100"
          >
            {submitting === "corrected" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Pencil className="h-4 w-4" />
            )}
            Save corrections
          </button>
        )}

        <button
          type="button"
          disabled={submitting !== null}
          onClick={() => handleSubmit("rejected")}
          className="btn-secondary flex items-center gap-1.5 text-red-600 hover:bg-red-50"
        >
          {submitting === "rejected" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <XCircle className="h-4 w-4" />
          )}
          Reject
        </button>
      </div>
    </div>
  );
}

/**
 * Parse a string input back to the appropriate type based on schema field_type.
 */
function parseFieldValue(
  raw: string,
  fieldType?: string,
): unknown {
  if (raw === "" || raw === "—") return null;

  const trimmed = raw.trim();

  switch (fieldType) {
    case "number": {
      const normalized = trimmed.replaceAll(",", "").replaceAll(" ", "");
      if (!normalized) return null;
      const n = Number(normalized);
      return Number.isNaN(n) ? raw : n;
    }
    case "boolean": {
      const normalized = trimmed.toLowerCase();
      if (["true", "yes", "1"].includes(normalized)) return true;
      if (["false", "no", "0"].includes(normalized)) return false;
      return raw;
    }
    case "date": {
      if (/^\d{4}-\d{2}-\d{2}/.test(trimmed)) {
        return trimmed.slice(0, 10);
      }
      const match = trimmed.match(/^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$/);
      if (match) {
        return `${match[3]}-${String(Number(match[1])).padStart(2, "0")}-${String(Number(match[2])).padStart(2, "0")}`;
      }
      return raw;
    }
    case "list":
      if (!trimmed) return [];
      if (trimmed.startsWith("[")) {
        try {
          const parsed = JSON.parse(trimmed);
          return Array.isArray(parsed) ? parsed : raw;
        } catch {
          return raw;
        }
      }
      return trimmed.split(",").map((item) => item.trim()).filter(Boolean);
    case "object":
      try {
        return JSON.parse(trimmed);
      } catch {
        return raw;
      }
    default:
      return raw;
  }
}
