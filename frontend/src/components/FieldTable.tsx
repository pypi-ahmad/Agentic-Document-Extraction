import { type ExtractionSchemaResponse } from "@/lib/api";

// ── Types ───────────────────────────────────────────────────────────

interface FieldTableProps {
  resultData: Record<string, unknown>;
  schema: ExtractionSchemaResponse | null;
  confidence?: Record<string, number> | null;
}

// ── Helpers ─────────────────────────────────────────────────────────

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return value.toLocaleString();
  if (Array.isArray(value) || typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function isStructuredValue(value: unknown): boolean {
  return Array.isArray(value) || (typeof value === "object" && value !== null);
}

function confidenceColor(score: number): string {
  // Color bands are decorative. The actual review-routing threshold
  // is controlled server-side via CONFIDENCE_THRESHOLD (default 0.6).
  if (score >= 0.8) return "text-green-600 bg-green-50";
  if (score >= 0.6) return "text-yellow-600 bg-yellow-50";
  return "text-red-600 bg-red-50";
}

// ── Component ───────────────────────────────────────────────────────

export default function FieldTable({
  resultData,
  schema,
  confidence,
}: FieldTableProps) {
  const fieldKeys: string[] = schema
    ? schema.fields.map((f) => f.name)
    : Object.keys(resultData);

  const schemaFieldMap = new Map(
    (schema?.fields ?? []).map((f) => [f.name, f]),
  );

  if (fieldKeys.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 px-4 py-6 text-center text-sm text-gray-400">
        No data was extracted from this document.
      </div>
    );
  }

  return (
    <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
      {fieldKeys.map((key) => {
        const value = resultData[key];
        const schemaDef = schemaFieldMap.get(key);
        const isMissing = value === null || value === undefined;
        const isRequired = schemaDef?.required ?? false;
        const score = confidence?.[key];

        return (
          <div key={key} className="px-4 py-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-gray-800">
                      {schemaDef?.description || key}
                    </span>
                    {schemaDef?.description && schemaDef.description !== key && (
                      <div className="text-xs text-gray-400">{key}</div>
                    )}
                  </div>
                  {isRequired && isMissing && (
                    <span className="badge badge-error">Missing</span>
                  )}
                  {!isRequired && isMissing && (
                    <span className="badge badge-pending">Not provided</span>
                  )}
                  {score != null && (
                    <span
                      className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium ${confidenceColor(score)}`}
                      title={`AI confidence: ${(score * 100).toFixed(0)}%`}
                    >
                      {(score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 text-right">
                {isStructuredValue(value) ? (
                  <pre
                    className={`max-w-md whitespace-pre-wrap break-words rounded bg-gray-50 px-2 py-1 text-left font-mono text-xs ${
                      isMissing ? "italic text-gray-400" : "text-gray-800"
                    }`}
                  >
                    {formatValue(value)}
                  </pre>
                ) : (
                  <span
                    className={`text-sm ${isMissing ? "italic text-gray-400" : "text-gray-900"}`}
                  >
                    {formatValue(value)}
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
