"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  createSchema,
  listSchemas,
  getSchemaPresets,
  createSchemaFromPreset,
  FieldType,
  type ExtractionSchemaResponse,
  type SchemaFieldDef,
  type SchemaPreset,
} from "@/lib/api";
import { Plus, Trash2, Save, Loader2, FileText } from "lucide-react";

const EMPTY_FIELD: SchemaFieldDef = {
  name: "",
  description: "",
  field_type: FieldType.STRING,
  required: true,
};

export default function SchemasPage() {
  const [schemas, setSchemas] = useState<ExtractionSchemaResponse[]>([]);
  const [presets, setPresets] = useState<SchemaPreset[]>([]);
  const [loadingInitialData, setLoadingInitialData] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [presetLoadError, setPresetLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [presetLoading, setPresetLoading] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [fields, setFields] = useState<SchemaFieldDef[]>([{ ...EMPTY_FIELD }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPageData = useCallback(async () => {
    setLoadingInitialData(true);
    setLoadError(null);
    setPresetLoadError(null);

    const [schemasResult, presetsResult] = await Promise.allSettled([
      listSchemas(),
      getSchemaPresets(),
    ]);

    if (schemasResult.status === "fulfilled") {
      setSchemas(schemasResult.value);
    } else {
      setSchemas([]);
      setLoadError(
        schemasResult.reason instanceof Error
          ? schemasResult.reason.message
          : "Could not load templates.",
      );
    }

    if (presetsResult.status === "fulfilled") {
      setPresets(presetsResult.value);
    } else {
      setPresets([]);
      setPresetLoadError(
        presetsResult.reason instanceof Error
          ? presetsResult.reason.message
          : "Preset templates are temporarily unavailable.",
      );
    }

    setLoadingInitialData(false);
  }, []);

  useEffect(() => {
    void loadPageData();
  }, [loadPageData]);

  const addField = () => setFields([...fields, { ...EMPTY_FIELD }]);

  const removeField = (idx: number) =>
    setFields(fields.filter((_, i) => i !== idx));

  const updateField = (idx: number, patch: Partial<SchemaFieldDef>) =>
    setFields(fields.map((f, i) => (i === idx ? { ...f, ...patch } : f)));

  const handleSave = async () => {
    if (!name.trim()) {
      setError("Template name is required");
      return;
    }
    if (fields.some((f) => !f.name.trim())) {
      setError("All fields must have a name");
      return;
    }
    setError(null);
    setSaving(true);

    try {
      const schema = await createSchema({
        name,
        description: description || undefined,
        fields,
      });
      setSchemas((current) => [schema, ...current]);
      setCreating(false);
      setName("");
      setDescription("");
      setFields([{ ...EMPTY_FIELD }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleUsePreset = async (preset: SchemaPreset) => {
    setError(null);
    setPresetLoading(preset.id);
    try {
      const schema = await createSchemaFromPreset(preset.id);
      setSchemas((current) => [schema, ...current]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(
          `A template named "${preset.name}" already exists. Review the preset below and save it with a new name.`,
        );
        setName(preset.name);
        setDescription(preset.description);
        setFields(
          preset.fields.map((f) => ({
            name: f.name,
            description: f.description,
            field_type: f.field_type,
            required: f.required,
          })),
        );
        setCreating(true);
      } else {
        setError(err instanceof Error ? err.message : "Could not use preset");
      }
    } finally {
      setPresetLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            Extraction Templates
          </h2>
          <p className="text-sm text-gray-500">
            Define what data to extract from your documents
          </p>
        </div>
        {!creating && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            <Plus className="h-4 w-4" /> New Template
          </button>
        )}
      </div>

      {loadingInitialData ? (
        <div className="card flex flex-col items-center justify-center gap-2 py-10 text-center">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          <p className="text-sm text-gray-500">Loading templates…</p>
        </div>
      ) : loadError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <p className="text-sm font-medium text-red-700">
            Could not load templates.
          </p>
          <p className="mt-1 text-sm text-red-600">{loadError}</p>
          <button
            type="button"
            onClick={() => void loadPageData()}
            className="mt-4 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          {presetLoadError && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {presetLoadError}
            </div>
          )}

          {/* Preset quick-start */}
          {!creating && presets.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-gray-700">
                Quick Start — Use a preset
              </h3>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {presets.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    disabled={presetLoading !== null}
                    onClick={() => handleUsePreset(preset)}
                    className="card text-left transition hover:shadow-md disabled:opacity-50"
                  >
                    <div className="flex items-start gap-3">
                      <FileText className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary-600" />
                      <div className="min-w-0">
                        <h4 className="font-semibold text-gray-900">
                          {preset.name}
                          {presetLoading === preset.id && (
                            <Loader2 className="ml-2 inline h-4 w-4 animate-spin text-primary-600" />
                          )}
                        </h4>
                        <p className="mt-0.5 text-sm text-gray-500">
                          {preset.description}
                        </p>
                        <p className="mt-2 text-xs text-gray-400">
                          {preset.fields.length} field
                          {preset.fields.length !== 1 ? "s" : ""} •{" "}
                          {preset.doc_type}
                        </p>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Create form */}
          {creating && (
            <div className="card space-y-4">
              <h3 className="text-lg font-semibold text-gray-900">New Template</h3>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Template Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Invoice, Receipt, Contract..."
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Description (optional)
                </label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What kind of documents is this for?"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              </div>

              {/* Fields */}
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">
                  Fields to Extract
                </label>
                <div className="space-y-3">
                  {fields.map((field, idx) => (
                    <div
                      key={idx}
                      className="grid grid-cols-12 gap-2 rounded-lg bg-gray-50 p-3"
                    >
                      <div className="col-span-3">
                        <input
                          type="text"
                          value={field.name}
                          onChange={(e) =>
                            updateField(idx, { name: e.target.value })
                          }
                          placeholder="Field name"
                          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                        />
                      </div>
                      <div className="col-span-4">
                        <input
                          type="text"
                          value={field.description}
                          onChange={(e) =>
                            updateField(idx, { description: e.target.value })
                          }
                          placeholder="Description (helps the AI)"
                          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                        />
                      </div>
                      <div className="col-span-2">
                        <select
                          value={field.field_type}
                          onChange={(e) =>
                            updateField(idx, { field_type: e.target.value as FieldType })
                          }
                          className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                        >
                          <option value="string">Text</option>
                          <option value="number">Number</option>
                          <option value="boolean">Yes/No</option>
                          <option value="date">Date</option>
                          <option value="list">List</option>
                          <option value="object">Object</option>
                        </select>
                      </div>
                      <div className="col-span-2 flex items-center gap-2">
                        <label className="flex items-center gap-1 text-xs text-gray-600">
                          <input
                            type="checkbox"
                            checked={field.required}
                            onChange={(e) =>
                              updateField(idx, { required: e.target.checked })
                            }
                            className="rounded"
                          />
                          Required
                        </label>
                      </div>
                      <div className="col-span-1 flex items-center justify-end">
                        {fields.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeField(idx)}
                            className="text-gray-400 hover:text-red-500"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={addField}
                  className="mt-2 flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700"
                >
                  <Plus className="h-3.5 w-3.5" /> Add field
                </button>
              </div>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saving}
                  className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  {saving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  {saving ? "Saving..." : "Save Template"}
                </button>
                <button
                  type="button"
                  onClick={() => setCreating(false)}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Existing schemas list */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {schemas.map((schema) => (
              <div key={schema.id} className="card">
                <h4 className="font-semibold text-gray-900">{schema.name}</h4>
                {schema.description && (
                  <p className="mt-1 text-sm text-gray-500">
                    {schema.description}
                  </p>
                )}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {schema.fields.map((f) => (
                    <span
                      key={f.name}
                      className="badge bg-gray-100 text-gray-700"
                    >
                      {f.name}
                    </span>
                  ))}
                </div>
                <p className="mt-3 text-xs text-gray-400">
                  {schema.fields.length} field
                  {schema.fields.length !== 1 ? "s" : ""}
                </p>
              </div>
            ))}
          </div>
          {schemas.length === 0 && !creating && (
            <div className="rounded-xl border-2 border-dashed border-gray-200 p-12 text-center">
              <p className="text-gray-500">No templates yet.</p>
              <p className="mt-1 text-sm text-gray-400">
                Create a template to define what data to extract from your documents.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
