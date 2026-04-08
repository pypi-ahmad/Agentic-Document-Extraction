"use client";

import { useEffect, useState } from "react";
import {
  getParsers,
  getLLMProviders,
  getLLMModels,
  listSchemas,
  startExtraction,
  LLMProviderID,
  ProviderAvailabilityState,
  ParserEngine,
  type LLMModelListResponse,
  type LLMProviderInfo,
  type ParserOptionInfo,
  type ModelInfo,
  type ExtractionSchemaResponse,
  type DocumentResponse,
  type ExtractionResponse,
} from "@/lib/api";
import { ChevronDown, ChevronUp, Play, Loader2 } from "lucide-react";

interface ExtractionFormProps {
  document: DocumentResponse;
  onStarted: (extraction: ExtractionResponse) => void;
}

export default function ExtractionForm({
  document,
  onStarted,
}: ExtractionFormProps) {
  const [schemas, setSchemas] = useState<ExtractionSchemaResponse[]>([]);
  const [parsers, setParsers] = useState<ParserOptionInfo[]>([]);
  const [llmProviders, setLlmProviders] = useState<LLMProviderInfo[]>([]);
  const [llmModels, setLlmModels] = useState<ModelInfo[]>([]);
  const [llmModelCatalog, setLlmModelCatalog] =
    useState<LLMModelListResponse | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);

  const [selectedSchema, setSelectedSchema] = useState("");
  const [ocrProvider, setOcrProvider] = useState<ParserEngine>(
    ParserEngine.AUTO,
  );
  const [llmProvider, setLlmProvider] = useState<LLMProviderID>(
    LLMProviderID.AUTO,
  );
  const [llmModel, setLlmModel] = useState("auto");

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load schemas and providers on mount
  useEffect(() => {
    listSchemas().then(setSchemas).catch(() => {});
    getParsers().then(setParsers).catch(() => {});
    getLLMProviders().then(setLlmProviders).catch(() => {});
  }, []);

  // Load models when AI provider changes
  useEffect(() => {
    if (llmProvider !== LLMProviderID.AUTO) {
      setModelsLoading(true);
      getLLMModels(llmProvider)
        .then((catalog) => {
          setLlmModelCatalog(catalog);
          setLlmModels(catalog.models);
        })
        .catch(() => {
          setLlmModelCatalog(null);
          setLlmModels([]);
        })
        .finally(() => setModelsLoading(false));
    } else {
      setLlmModelCatalog(null);
      setLlmModels([]);
    }
    setLlmModel("auto");
  }, [llmProvider]);

  const handleSubmit = async () => {
    if (!selectedSchema) {
      setError("Please select an extraction template.");
      return;
    }
    setError(null);
    setSubmitting(true);

    try {
      const extraction = await startExtraction({
        document_id: document.id,
        schema_id: selectedSchema,
        ocr_provider: ocrProvider,
        llm_provider: llmProvider,
        llm_model: llmModel,
      });
      onStarted(extraction);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start extraction",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const getParserHint = (p: ParserOptionInfo): string => {
    if (!p.enabled) return " (disabled)";
    if (!p.available) return " (not installed)";
    return "";
  };

  const getProviderHint = (p: LLMProviderInfo): string => {
    switch (p.availability.state) {
      case ProviderAvailabilityState.MISSING_API_KEY:
        return " (API key not set)";
      case ProviderAvailabilityState.CLIENT_NOT_INSTALLED:
        return " (not installed)";
      case ProviderAvailabilityState.ERROR:
        return " (unavailable)";
      default:
        return "";
    }
  };

  const selectCls =
    "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500";

  return (
    <div className="card space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-gray-900">Extract Data</h3>
        <p className="text-sm text-gray-500">
          From:{" "}
          <span className="font-medium">{document.original_filename}</span>
        </p>
      </div>

      {/* Schema selector */}
      <div>
        <label className="mb-1.5 block text-sm font-medium text-gray-700">
          What do you want to extract?
        </label>
        <select
          value={selectedSchema}
          onChange={(e) => {
            setSelectedSchema(e.target.value);
            setError(null);
          }}
          className={selectCls}
        >
          <option value="">Select a template…</option>
          {schemas.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        {schemas.length === 0 && (
          <p className="mt-1 text-xs text-gray-400">
            No templates yet.{" "}
            <a href="/schemas" className="text-primary-600 hover:underline">
              Create one first
            </a>
          </p>
        )}
      </div>

      {/* Processing options (hidden by default) */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-700"
      >
        {showAdvanced ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
        Advanced settings
      </button>

      {showAdvanced && (
        <div className="space-y-4 rounded-lg bg-gray-50 p-4">
          {/* Document parser */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Document Reader
            </label>
            <select
              value={ocrProvider}
              onChange={(e) =>
                setOcrProvider(e.target.value as ParserEngine)
              }
              className={selectCls}
            >
              <option value={ParserEngine.AUTO}>Auto (recommended)</option>
              {parsers.map((p) => (
                <option
                  key={p.id}
                  value={p.id}
                  disabled={!p.enabled || !p.available}
                >
                  {p.name}
                  {getParserHint(p)}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-400">
              How the text is read from your document. PaddleOCR requires
              separate install for image files.
            </p>
          </div>

          {/* AI provider */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              AI Provider
            </label>
            <select
              value={llmProvider}
              onChange={(e) =>
                setLlmProvider(e.target.value as LLMProviderID)
              }
              className={selectCls}
            >
              <option value={LLMProviderID.AUTO}>Auto (recommended)</option>
              {llmProviders.map((p) => (
                <option key={p.id} value={p.id} disabled={!p.available}>
                  {p.name}
                  {getProviderHint(p)}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-400">
              Which AI service extracts the data. Requires a valid API key.
            </p>
          </div>

          {/* AI model — only when a specific provider is chosen */}
          {llmProvider !== LLMProviderID.AUTO && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                AI Model
              </label>
              {modelsLoading ? (
                <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Loading available models…
                </div>
              ) : (
                <select
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                  className={selectCls}
                >
                  <option value="auto">Auto (recommended)</option>
                  {llmModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                      {m.is_default ? " ★" : ""}
                    </option>
                  ))}
                </select>
              )}
              {llmModelCatalog?.error && (
                <p className="mt-1 text-xs text-amber-600">
                  Could not load models: {llmModelCatalog.error.message}
                </p>
              )}
              {!modelsLoading &&
                !llmModelCatalog?.error &&
                llmModels.length === 0 && (
                  <p className="mt-1 text-xs text-gray-400">
                    No models available from this provider.
                  </p>
                )}
            </div>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={submitting || !selectedSchema}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Play className="h-4 w-4" />
        )}
        {submitting ? "Starting…" : "Start Extraction"}
      </button>
    </div>
  );
}
