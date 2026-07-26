"use client";

import { useEffect, useState } from "react";
import { Check, Plus, Save, Trash2 } from "lucide-react";

import {
  createExtractionSchema,
  deleteExtractionSchema,
  listExtractionSchemas,
  updateExtractionSchema,
  validateExtractionSchema,
  type ExtractionSchema,
} from "@/lib/api";

const EMPTY_SCHEMA = JSON.stringify({
  $schema: "https://json-schema.org/draft/2020-12/schema",
  type: "object",
  properties: {},
  required: [],
  additionalProperties: false,
}, null, 2);

export function SchemaWorkspace({ onChanged }: { onChanged: (items: ExtractionSchema[]) => void }) {
  const [items, setItems] = useState<ExtractionSchema[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("Untitled extraction");
  const [description, setDescription] = useState("");
  const [source, setSource] = useState(EMPTY_SCHEMA);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh(preferredId?: string) {
    const next = await listExtractionSchemas();
    setItems(next);
    onChanged(next);
    if (preferredId) select(next.find((item) => item.id === preferredId) ?? null);
  }

  useEffect(() => { void refresh().catch((error) => setMessage(error.message)); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function select(item: ExtractionSchema | null) {
    setSelectedId(item?.id ?? null);
    setName(item?.name ?? "Untitled extraction");
    setDescription(item?.description ?? "");
    setSource(item ? JSON.stringify(item.json_schema, null, 2) : EMPTY_SCHEMA);
    setMessage(null);
  }

  function addField() {
    try {
      const schema = JSON.parse(source) as { properties?: Record<string, unknown> };
      const base = "new_field";
      let field = base;
      let index = 2;
      schema.properties ??= {};
      while (field in schema.properties) field = `${base}_${index++}`;
      schema.properties[field] = { type: "string", description: "Value to extract" };
      setSource(JSON.stringify(schema, null, 2));
      setMessage(`Added ${field}. Edit its type or nest object/array properties in JSON.`);
    } catch {
      setMessage("Fix the JSON before adding a field.");
    }
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const json_schema = JSON.parse(source) as Record<string, unknown>;
      const validation = await validateExtractionSchema(json_schema);
      if (!validation.valid || !validation.normalized_schema) {
        setMessage(validation.errors.map((item) => `${item.path || "/"}: ${item.message}`).join(" · "));
        return;
      }
      const body = { name, description: description || null, json_schema: validation.normalized_schema };
      const saved = selectedId
        ? await updateExtractionSchema(selectedId, body)
        : await createExtractionSchema(body);
      await refresh(saved.id);
      setMessage(`Saved version ${saved.version}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Schema could not be saved");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selectedId || !window.confirm("Delete this extraction schema? Existing jobs keep their snapshot.")) return;
    setBusy(true);
    try {
      await deleteExtractionSchema(selectedId);
      select(null);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Schema could not be deleted");
    } finally {
      setBusy(false);
    }
  }

  return <section className="schema-workspace">
    <aside className="schema-list"><div><strong>Saved schemas</strong><button type="button" onClick={() => select(null)}><Plus size={14} /> New</button></div>{items.map((item) => <button type="button" className={selectedId === item.id ? "active" : ""} key={item.id} onClick={() => select(item)}><span>{item.name}</span><small>v{item.version}</small></button>)}{!items.length && <p>No saved schemas yet.</p>}</aside>
    <div className="schema-editor">
      <div className="schema-editor-head"><div><span>Schema-first extraction</span><h2>{selectedId ? "Edit schema" : "Create schema"}</h2><p>Draft 2020-12 restricted subset. Mark table arrays with <code>x-paperplane-kind: &quot;table&quot;</code>.</p></div><div><button type="button" className="secondary-button" onClick={addField}><Plus size={15} /> Add string field</button>{selectedId && <button type="button" className="secondary-button danger" onClick={() => void remove()} disabled={busy}><Trash2 size={15} /> Delete</button>}<button type="button" className="parse-button" onClick={() => void save()} disabled={busy || !name.trim()}><Save size={15} /> Save</button></div></div>
      <label htmlFor="schema-name">Name</label><input id="schema-name" value={name} maxLength={255} onChange={(event) => setName(event.target.value)} />
      <label htmlFor="schema-description">Description</label><input id="schema-description" value={description} maxLength={2000} onChange={(event) => setDescription(event.target.value)} placeholder="What should this schema extract?" />
      <label htmlFor="schema-json">JSON Schema</label><textarea id="schema-json" spellCheck={false} value={source} onChange={(event) => setSource(event.target.value)} />
      {message && <p className="schema-message"><Check size={14} /> {message}</p>}
    </div>
  </section>;
}
