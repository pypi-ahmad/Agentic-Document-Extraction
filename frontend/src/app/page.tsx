"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type DragEvent,
} from "react";
import {
  AlertCircle,
  Check,
  ChevronDown,
  Download,
  FileText,
  Info,
  Loader2,
  LockKeyhole,
  Moon,
  Paperclip,
  Plane,
  Plus,
  Square,
  Sun,
  UploadCloud,
  X,
} from "lucide-react";
import {
  apiResourceUrl,
  artifactUrl,
  cancelJob,
  createEvaluationRun,
  createJob,
  createParseBatch,
  evaluateJob,
  getEvaluationRun,
  getJob,
  getMarkdown,
  getRuntimeCapabilities,
  listJobs,
  listParseBatches,
  listEvaluationRuns,
  listExtractionSchemas,
  listOllamaModels,
  type OllamaModel,
  type EvaluationRun,
  type ExtractionSchema,
  type ParseJob,
  type ParseBatch,
  type ParseSettings,
  type VisionModel,
  type VisionProvider,
} from "@/lib/api";
import { ArtifactGallery } from "@/components/ArtifactGallery";
import { SubDocumentGallery } from "@/components/SubDocumentGallery";
import { SchemaWorkspace } from "@/components/SchemaWorkspace";
import { DocumentInspector } from "@/components/DocumentInspector";

const DEFAULT_SETTINGS: ParseSettings = {
  segment_documents: true,
  document_profile: "auto",
  structured_extraction: true,
  allow_sensitive_cloud: false,
  processing_mode: "local_only",
  quality_overrides: {},
  ocr_provider: "ollama",
  ocr_model: null,
  review_provider: "ollama",
  review_model: null,
  extraction_schema_id: null,
  extraction_provider: "ollama",
  extraction_model: null,
  cloud_mode: "off",
  blind_local_retry: false,
  start_page: 1,
  end_page: null,
  input_mode: "mixed",
  dpi: 200,
  describe_figures: true,
  marginalia_policy: "remove_repeated",
  grounding_pdf: true,
  searchable_pdf: true,
  bundle: true,
};
const TERMINAL = new Set(["completed", "completed_with_warnings", "failed", "cancelled", "paused"]);
const CANCELLABLE = new Set(["queued", "inspecting", "processing", "assembling"]);
const MODEL_STORAGE_KEY = "paperplane:model-selection:v1";
const THEME_STORAGE_KEY = "paperplane:theme:v1";
const SUPPORTED_EXTENSIONS = new Set(["pdf", "png", "jpg", "jpeg", "tif", "tiff"]);

const HELP = {
  segmentDocuments: "Detect mixed document types and repeated identifiers, then create classified page-range artifacts without rerunning OCR.",
  documentProfile: "Auto detects a document family from the first local batch. Choose a profile to force its validated extraction schema.",
  structuredExtraction: "Creates evidence-grounded domain JSON. Every non-empty value cites its source page, region, and bounding box.",
  extractionSchema: "Applies a saved schema to each detected sub-document and to the parent document. Values retain page, bounding-box, and table-cell citations.",
  extractionModel: "Dedicated model for unresolved schema fields. Local-only uses Ollama; hybrid and maximum-accuracy may use a configured cloud provider.",
  sensitiveCloud: "Explicitly permits page images and extracted text to leave this device. Required for healthcare and insurance cloud processing.",
  ocrModel: "GLM-OCR runs locally after PaddleOCR-VL and transcribes every eligible region in scanned mode. It also performs targeted repair passes.",
  reviewProvider: "Optional cloud context stage. It receives flagged rendered pages, draft Markdown, region IDs, and local OCR candidates.",
  reviewModel: "Adjudicates uncertain local OCR results and returns region-specific repair instructions without changing layout geometry.",
  processingMode: "Local only never calls a cloud provider. Hybrid escalates flagged pages. Maximum accuracy reviews every selected page and enables a blind local retry.",
  blindRetry: "After a cloud disagreement, run one fresh local GLM crop without sending GLM the cloud verdict, hint, or proposed answer.",
  inputMode: "Mixed combines visual layout with embedded PDF text. Native uses embedded text when present. Scanned relies on image layout and OCR.",
  dpi: "Higher DPI sharpens small text but increases processing time and memory use.",
  pageRange: "Process an inclusive, one-based page range. Leave the last page blank to continue through the document.",
  marginalia: "Remove repeated omits page numbers and repeated headers or footers from clean Markdown. Keep all retains them.",
  figures: "Use the optional repair model for richer figure descriptions. Figure crops are still created when this is off.",
  annotated: "Always creates a PDF showing detected regions, IDs, and bounding boxes.",
  searchable: "Adds an invisible text layer to a PDF. This costs extra processing time and storage.",
  bundle: "Packages the source and generated outputs into one ZIP download.",
};

function statusLabel(status: string) {
  return status.split("_").map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
}

function elapsed(job: ParseJob) {
  if (!job.started_at) return "—";
  const end = job.completed_at ? new Date(job.completed_at).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((end - new Date(job.started_at).getTime()) / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function savedModels(): Partial<ParseSettings> {
  try {
    return JSON.parse(window.localStorage.getItem(MODEL_STORAGE_KEY) ?? "{}") as Partial<ParseSettings>;
  } catch {
    window.localStorage.removeItem(MODEL_STORAGE_KEY);
    return {};
  }
}

export default function HomePage() {
  const [workspaceMode, setWorkspaceMode] = useState<"parse" | "evaluate" | "schemas">("parse");
  const [jobs, setJobs] = useState<ParseJob[]>([]);
  const [active, setActive] = useState<ParseJob | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [activeBatch, setActiveBatch] = useState<ParseBatch | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stoppingJobId, setStoppingJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [providers, setProviders] = useState<VisionProvider[]>([]);
  const [extractionSchemas, setExtractionSchemas] = useState<ExtractionSchema[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [parserAvailable, setParserAvailable] = useState<boolean | null>(null);
  const [parserModel, setParserModel] = useState("PaddleOCR-VL-1.6");
  const [parserError, setParserError] = useState<string | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [evaluationRuns, setEvaluationRuns] = useState<EvaluationRun[]>([]);
  const [activeEvaluation, setActiveEvaluation] = useState<EvaluationRun | null>(null);
  const [evaluationJobId, setEvaluationJobId] = useState("");
  const [goldFile, setGoldFile] = useState<File | null>(null);
  const [datasetFile, setDatasetFile] = useState<File | null>(null);
  const [evaluationBusy, setEvaluationBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const activeId = active?.id;
  const activeStatus = active?.status;
  const markdownArtifact = active?.artifacts.find((item) => item.type === "clean_markdown");
  const markdownArtifactId = markdownArtifact?.id;
  const markdownDownloadUrl = markdownArtifact?.download_url;
  const compatibleModels = models.filter((model) => model.compatible);
  const cloudSelected = (settings.cloud_mode !== "off" && settings.review_provider !== "ollama")
    || (Boolean(settings.extraction_schema_id) && settings.extraction_provider !== "ollama");
  const providerModels = useCallback((provider: ParseSettings["ocr_provider"]): VisionModel[] => {
    if (provider === "ollama") {
      return compatibleModels.map((model) => ({ id: model.name, name: model.name }));
    }
    return providers.find((item) => item.id === provider)?.models ?? [];
  }, [compatibleModels, providers]);

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [next, batches] = await Promise.all([listJobs(), listParseBatches()]);
      setJobs(next);
      setActive((current) => current ? next.find((job) => job.id === current.id) ?? current : next[0] ?? null);
      setActiveBatch((current) => current ? batches.find((batch) => batch.id === current.id) ?? current : batches[0] ?? null);
    } catch {
      // Model discovery displays the actionable backend status.
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    if (!activeBatch || ["completed", "completed_with_errors", "failed", "cancelled"].includes(activeBatch.status)) return;
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(timer);
  }, [activeBatch, refresh]);

  const refreshEvaluations = useCallback(async () => {
    const next = await listEvaluationRuns().catch(() => []);
    setEvaluationRuns(next);
    setActiveEvaluation((current) => current ? next.find((run) => run.id === current.id) ?? current : next[0] ?? null);
  }, []);

  useEffect(() => {
    if (workspaceMode === "evaluate") void refreshEvaluations();
  }, [workspaceMode, refreshEvaluations]);

  useEffect(() => {
    const run = activeEvaluation;
    if (!run || !["pending", "running"].includes(run.status)) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      void getEvaluationRun(run.id, controller.signal).then((next) => {
        setActiveEvaluation(next);
        setEvaluationRuns((items) => items.map((item) => item.id === next.id ? next : item));
      }).catch(() => undefined);
    }, 1500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [activeEvaluation]);

  const refreshModels = useCallback(async (force = false) => {
    setModelsLoading(true);
    setModelError(null);
    try {
      const installed = await listOllamaModels(force);
      const compatible = installed.filter((model) => model.compatible);
      const saved = savedModels();
      const valid = (name: unknown) => typeof name === "string" && compatible.some((model) => model.name === name);
      setModels(installed);
      setSettings((current) => ({
        ...current,
        ocr_model: current.ocr_provider === "ollama"
          ? valid(current.ocr_model) ? current.ocr_model : valid(saved.ocr_model) ? saved.ocr_model! : compatible[0]?.name ?? null
          : current.ocr_model,
        review_model: current.review_provider === "ollama" ? null : current.review_model,
        extraction_model: current.extraction_provider === "ollama"
          ? valid(current.extraction_model) ? current.extraction_model : compatible[0]?.name ?? null
          : current.extraction_model,
      }));
    } catch (caught) {
      setModels([]);
      setSettings((current) => ({
        ...current,
        ocr_model: current.ocr_provider === "ollama" ? null : current.ocr_model,
        review_model: current.review_provider === "ollama" ? null : current.review_model,
        extraction_model: current.extraction_provider === "ollama" ? null : current.extraction_model,
      }));
      setModelError(caught instanceof Error ? caught.message : "Ollama is unavailable");
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => { void refreshModels(); }, [refreshModels]);
  useEffect(() => { void listExtractionSchemas().then(setExtractionSchemas).catch(() => setExtractionSchemas([])); }, []);
  useEffect(() => {
    void getRuntimeCapabilities().then((capabilities) => {
      setParserAvailable(capabilities.paddleocr_vl_available);
      setParserModel(capabilities.parser_model);
      setParserError(capabilities.paddleocr_vl.error);
      setProviders(capabilities.providers);
    }).catch(() => {
      setParserAvailable(false);
      setParserError("Backend runtime capabilities are unavailable");
    });
  }, []);
  useEffect(() => {
    window.localStorage.setItem(MODEL_STORAGE_KEY, JSON.stringify({
      ocr_provider: settings.ocr_provider,
      ocr_model: settings.ocr_model,
      review_provider: settings.review_provider,
      review_model: settings.review_model,
      processing_mode: settings.processing_mode,
      cloud_mode: settings.cloud_mode,
      blind_local_retry: settings.blind_local_retry,
      extraction_schema_id: settings.extraction_schema_id,
      extraction_provider: settings.extraction_provider,
      extraction_model: settings.extraction_model,
    }));
  }, [settings.ocr_provider, settings.ocr_model, settings.review_provider, settings.review_model, settings.processing_mode, settings.cloud_mode, settings.blind_local_retry, settings.extraction_schema_id, settings.extraction_provider, settings.extraction_model]);

  function changeCloudProvider(provider: ParseSettings["review_provider"] | "off") {
    if (provider === "off") {
      setSettings((current) => ({
        ...current,
        review_provider: "ollama",
        review_model: null,
        processing_mode: "local_only",
        cloud_mode: "off",
        blind_local_retry: false,
      }));
      return;
    }
    const firstModel = providerModels(provider)[0]?.id ?? null;
    setSettings((current) => ({
      ...current,
      review_provider: provider,
      review_model: firstModel,
      processing_mode: current.processing_mode === "maximum_accuracy" ? "maximum_accuracy" : "hybrid",
      cloud_mode: current.processing_mode === "maximum_accuracy" ? "all_pages" : "adaptive",
    }));
  }

  function changeProcessingMode(processing_mode: ParseSettings["processing_mode"]) {
    if (processing_mode === "local_only") {
      setSettings((current) => ({
        ...current,
        processing_mode: "local_only",
        cloud_mode: "off",
        review_provider: "ollama",
        review_model: null,
        blind_local_retry: false,
        extraction_provider: "ollama",
        extraction_model: providerModels("ollama")[0]?.id ?? null,
      }));
      return;
    }
    const readyProvider = settings.review_provider !== "ollama"
      ? settings.review_provider
      : providers.find((provider) => provider.id !== "ollama" && provider.state === "ready")?.id;
    const reviewModel = readyProvider
      ? (settings.review_provider === readyProvider && settings.review_model
          ? settings.review_model
          : providerModels(readyProvider)[0]?.id ?? null)
      : null;
    setSettings((current) => ({
      ...current,
      processing_mode,
      review_provider: readyProvider ?? "ollama",
      review_model: reviewModel,
      cloud_mode: processing_mode === "hybrid" ? "adaptive" : "all_pages",
      blind_local_retry: processing_mode === "maximum_accuracy" ? true : current.blind_local_retry,
    }));
  }

  useEffect(() => {
    const jobId = activeId;
    if (!jobId || !activeStatus || TERMINAL.has(activeStatus)) return;
    const controller = new AbortController();
    let current = true;
    let polling = false;
    const timer = window.setInterval(async () => {
      if (polling) return;
      polling = true;
      const next = await getJob(jobId, controller.signal).catch(() => null);
      polling = false;
      if (next && current && !controller.signal.aborted) {
        setActive((selected) => selected?.id === jobId ? next : selected);
        setJobs((items) => items.map((item) => item.id === next.id ? next : item));
      }
    }, 1000);
    return () => {
      current = false;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [activeId, activeStatus]);

  useEffect(() => {
    const jobId = activeId;
    const artifact = markdownDownloadUrl ? { download_url: markdownDownloadUrl } : null;
    setMarkdown("");
    if (!jobId || !artifact) return;
    const controller = new AbortController();
    let current = true;
    void getMarkdown(artifact, controller.signal).then((value) => {
      if (current && !controller.signal.aborted) setMarkdown(value);
    }).catch(() => {
      if (current && !controller.signal.aborted) setMarkdown("");
    });
    return () => {
      current = false;
      controller.abort();
    };
  }, [activeId, markdownArtifactId, markdownDownloadUrl]);

  function stageFiles(files: FileList | null) {
    if (!files?.length) return;
    const selected = Array.from(files);
    if (selected.some((file) => !SUPPORTED_EXTENSIONS.has(file.name.toLowerCase().split(".").pop() ?? ""))) {
      setError("Choose a PDF, PNG, JPEG, or TIFF document.");
      return;
    }
    setError(null);
    setPendingFiles(selected);
    setPendingFile(selected[0]);
    setActive(null);
    setMarkdown("");
  }

  async function parsePending() {
    if (!pendingFile) return;
    if (!parserAvailable) {
      setError(parserError ?? "PaddleOCR-VL Docker runtime is unavailable.");
      return;
    }
    if (settings.processing_mode !== "local_only" && (settings.review_provider === "ollama" || !settings.review_model)) {
      setError("Choose a configured cloud provider and model for this processing mode.");
      return;
    }
    if (settings.processing_mode !== "local_only" && (settings.document_profile === "insurance_claim" || settings.document_profile === "healthcare_form") && !settings.allow_sensitive_cloud) {
      setError("Explicitly allow sensitive cloud processing or choose Local only.");
      return;
    }
    const extension = pendingFile.name.toLowerCase().split(".").pop();
    setBusy(true);
    setError(null);
    try {
      if (pendingFiles.length > 1) {
        const batch = await createParseBatch(pendingFiles, settings);
        setActiveBatch(batch);
        setPendingFiles([]); setPendingFile(null);
        setJobs((items) => [...batch.jobs, ...items.filter((item) => !batch.jobs.some((job) => job.id === item.id))]);
        setActive(batch.jobs[0] ?? null);
        return;
      }
      const job = await createJob(pendingFile, extension === "pdf" ? settings : { ...settings, input_mode: "scanned" });
      setPendingFiles([]);
      setPendingFile(null);
      setActive(job);
      setJobs((items) => [job, ...items.filter((item) => item.id !== job.id)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function runSingleEvaluation() {
    if (!evaluationJobId || !goldFile) {
      setError("Choose a completed parse job and a grounded-label JSON file.");
      return;
    }
    setEvaluationBusy(true);
    setError(null);
    try {
      const run = await evaluateJob(evaluationJobId, goldFile);
      setActiveEvaluation(run);
      setEvaluationRuns((items) => [run, ...items.filter((item) => item.id !== run.id)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Evaluation failed");
    } finally {
      setEvaluationBusy(false);
    }
  }

  async function runBatchEvaluation() {
    if (!datasetFile) {
      setError("Choose a Paperplane evaluation dataset ZIP.");
      return;
    }
    if (settings.processing_mode !== "local_only" && (settings.review_provider === "ollama" || !settings.review_model)) {
      setError("Choose a configured cloud provider and model for this processing mode.");
      return;
    }
    setEvaluationBusy(true);
    setError(null);
    try {
      const run = await createEvaluationRun(datasetFile, settings);
      setActiveEvaluation(run);
      setEvaluationRuns((items) => [run, ...items.filter((item) => item.id !== run.id)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Evaluation dataset submission failed");
    } finally {
      setEvaluationBusy(false);
    }
  }

  async function stopActive() {
    const jobId = active?.id;
    if (!jobId || stoppingJobId === jobId || !CANCELLABLE.has(active.status)) return;
    setStoppingJobId(jobId);
    setError(null);
    try {
      const job = await cancelJob(jobId);
      setActive((selected) => selected?.id === jobId ? job : selected);
      setJobs((items) => items.map((item) => item.id === jobId ? job : item));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not stop parse job");
    } finally {
      setStoppingJobId((current) => current === jobId ? null : current);
    }
  }

  function removePending() {
    setPendingFile(null);
    setPendingFiles([]);
  }

  function selectJob(job: ParseJob) {
    setPendingFile(null);
    setActive(job);
  }

  function handleDragEnter(event: DragEvent<HTMLElement>) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    dragDepthRef.current += 1;
    setDragging(true);
  }

  function handleDragLeave(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (!dragDepthRef.current) setDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    dragDepthRef.current = 0;
    setDragging(false);
    stageFiles(event.dataTransfer.files);
  }

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
    setTheme(next);
  }

  const selectedPageCount = active?.pages.length ?? 0;
  const selectedPageTotal = Math.max(selectedPageCount, 1);
  const stopping = Boolean(active && (active.status === "cancelling" || stoppingJobId === active.id));
  const healthState = parserAvailable === null ? "loading" : parserAvailable ? "ready" : "error";
  const healthText = parserAvailable === null
    ? "Checking PaddleOCR-VL"
    : parserAvailable
      ? `${parserModel} ready`
      : "PaddleOCR-VL unavailable";

  return (
    <main
      className="app-shell"
      onDragEnter={handleDragEnter}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {dragging && <div className="drop-overlay" aria-hidden="true"><UploadCloud size={34} /><strong>Drop documents to prepare them</strong><span>PDF and image batches supported</span></div>}
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><Plane size={19} fill="currentColor" /></span><span>Paperplane</span></div>
        <button className="new-button" disabled={busy} onClick={() => inputRef.current?.click()}><Plus size={17} /> New document</button>
        <input
          ref={inputRef}
          hidden
          type="file"
          multiple
          accept="application/pdf,image/png,image/jpeg,image/tiff,.pdf,.png,.jpg,.jpeg,.tif,.tiff"
          onChange={(event) => {
            stageFiles(event.currentTarget.files);
            event.currentTarget.value = "";
          }}
        />
        <p className="side-label">Recent documents</p>
        <div className="job-list">
          {jobs.map((job) => <button key={job.id} className={`job-row ${active?.id === job.id ? "active" : ""}`} onClick={() => selectJob(job)}>
            <FileText size={17} /><span><strong>{job.original_filename}</strong><small>{statusLabel(job.status)} · {elapsed(job)}</small></span><i className={`status-dot ${job.status}`} />
          </button>)}
          {!jobs.length && <p className="empty-history">Your parsed documents will appear here.</p>}
        </div>
        <div className="privacy"><LockKeyhole size={19} /><div><strong>{cloudSelected ? "Cloud context enabled" : "Local processing"}</strong><p>{cloudSelected ? "Flagged page images, draft Markdown, and local OCR candidates are sent to the selected provider." : "Your documents stay on this device. PaddleOCR-VL and GLM-OCR run locally."}</p></div></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><h1>{workspaceMode === "parse" ? "Document to Markdown" : workspaceMode === "evaluate" ? "Extraction evaluation" : "Extraction schemas"}</h1><p><span className={`health-dot ${healthState}`} /> {healthText}</p></div>
          <div className="topbar-actions">
            <div className="workspace-switch" aria-label="Workspace mode"><button type="button" className={workspaceMode === "parse" ? "active" : ""} onClick={() => setWorkspaceMode("parse")}>Parse</button><button type="button" className={workspaceMode === "schemas" ? "active" : ""} onClick={() => setWorkspaceMode("schemas")}>Schemas</button><button type="button" className={workspaceMode === "evaluate" ? "active" : ""} onClick={() => setWorkspaceMode("evaluate")}>Evaluate</button></div>
            <button className="icon-button" type="button" onClick={toggleTheme} aria-label={theme === "dark" ? "Use light theme" : "Use dark theme"}>{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button>
            <button className="settings-button" aria-expanded={showSettings} aria-controls="parse-settings" onClick={() => setShowSettings(!showSettings)}>Parse settings <ChevronDown size={15} /></button>
          </div>
        </header>

        {showSettings && <section className="settings-panel" id="parse-settings">
          <SettingField id="document-profile" label="Document profile" help={HELP.documentProfile}><select id="document-profile" value={settings.document_profile} onChange={(event) => setSettings({ ...settings, document_profile: event.target.value as ParseSettings["document_profile"], allow_sensitive_cloud: false })}><option value="auto">Auto detect</option><option value="technical_document">Technical documentation</option><option value="scientific_paper">Scientific paper</option><option value="invoice">Invoice</option><option value="insurance_claim">Insurance claim</option><option value="healthcare_form">Healthcare form</option><option value="general_scanned">General scanned document</option></select></SettingField>
          <SettingCheckbox id="structured-extraction" label="Structured domain JSON" help={HELP.structuredExtraction} checked={settings.structured_extraction} onChange={(structured_extraction) => setSettings({ ...settings, structured_extraction })} />
          <SettingField id="extraction-schema" label="Custom extraction schema" help={HELP.extractionSchema}><select id="extraction-schema" value={settings.extraction_schema_id ?? ""} onChange={(event) => setSettings({ ...settings, extraction_schema_id: event.target.value || null })}><option value="">Disabled</option>{extractionSchemas.map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.version}</option>)}</select></SettingField>
          {settings.extraction_schema_id && <SettingField id="extraction-provider" label="Extraction provider" help={HELP.extractionModel}><select id="extraction-provider" value={settings.extraction_provider} onChange={(event) => { const extraction_provider = event.target.value as ParseSettings["extraction_provider"]; setSettings({ ...settings, extraction_provider, extraction_model: providerModels(extraction_provider)[0]?.id ?? null }); }}><option value="ollama">Ollama · local</option>{settings.processing_mode !== "local_only" && providers.filter((provider) => provider.id !== "ollama").map((provider) => <option key={provider.id} value={provider.id} disabled={provider.state !== "ready"}>{provider.name}{provider.state === "ready" ? "" : " · API key required"}</option>)}</select></SettingField>}
          {settings.extraction_schema_id && <ModelSelect id="extraction-model" label="Extraction model" help={HELP.extractionModel} value={settings.extraction_model} models={providerModels(settings.extraction_provider)} loading={settings.extraction_provider === "ollama" && modelsLoading} onChange={(extraction_model) => setSettings({ ...settings, extraction_model })} />}
          <SettingCheckbox id="segment-documents" label="Split mixed documents" help={HELP.segmentDocuments} checked={settings.segment_documents} onChange={(segment_documents) => setSettings({ ...settings, segment_documents })} />
          <ModelSelect id="ocr-model" label="Local OCR model" help={HELP.ocrModel} value={settings.ocr_model} models={providerModels("ollama")} loading={modelsLoading} onChange={(ocr_model) => setSettings({ ...settings, ocr_provider: "ollama", ocr_model })} />
          <SettingField id="processing-mode" label="Processing mode" help={HELP.processingMode}><select id="processing-mode" value={settings.processing_mode} onChange={(event) => changeProcessingMode(event.target.value as ParseSettings["processing_mode"])}><option value="local_only">Local only</option><option value="hybrid">Hybrid — flagged pages</option><option value="maximum_accuracy">Maximum accuracy — every page</option></select></SettingField>
          <details className="advanced-quality"><summary>Advanced quality thresholds</summary><SettingField id="minimum-confidence" label="Minimum region confidence" help="Override the profile-aware preset. Leave blank to use the resolved policy."><input id="minimum-confidence" type="number" min="0" max="1" step="0.01" value={settings.quality_overrides.min_region_confidence ?? ""} placeholder="Preset" onChange={(event) => setSettings({ ...settings, quality_overrides: { ...settings.quality_overrides, min_region_confidence: event.target.value ? Number(event.target.value) : undefined } })} /></SettingField><SettingField id="minimum-overall" label="Minimum overall quality" help="Regions below this gate are repaired or queued for review."><input id="minimum-overall" type="number" min="0" max="1" step="0.01" value={settings.quality_overrides.min_overall ?? ""} placeholder="Preset" onChange={(event) => setSettings({ ...settings, quality_overrides: { ...settings.quality_overrides, min_overall: event.target.value ? Number(event.target.value) : undefined } })} /></SettingField><SettingField id="maximum-repairs" label="Maximum repairs" help="Bounded per-page repair passes; the server maximum is two."><input id="maximum-repairs" type="number" min="0" max="2" step="1" value={settings.quality_overrides.max_repairs ?? ""} placeholder="2" onChange={(event) => setSettings({ ...settings, quality_overrides: { ...settings.quality_overrides, max_repairs: event.target.value ? Number(event.target.value) : undefined } })} /></SettingField></details>
          {settings.processing_mode !== "local_only" && <CloudProviderSelect id="review-provider" label="Cloud context provider" help={HELP.reviewProvider} value={settings.review_provider === "ollama" ? "off" : settings.review_provider} providers={providers} onChange={changeCloudProvider} />}
          {settings.processing_mode !== "local_only" && settings.review_provider !== "ollama" && <ModelSelect id="review-model" label="Cloud context model" help={HELP.reviewModel} value={settings.review_model} models={providerModels(settings.review_provider)} loading={false} onChange={(review_model) => setSettings({ ...settings, review_model })} />}
          {settings.processing_mode === "hybrid" && settings.review_provider !== "ollama" && <SettingCheckbox id="blind-local-retry" label="Blind local retry on cloud disagreement" help={HELP.blindRetry} checked={settings.blind_local_retry} onChange={(blind_local_retry) => setSettings({ ...settings, blind_local_retry })} />}
          {cloudSelected && (settings.document_profile === "auto" || settings.document_profile === "insurance_claim" || settings.document_profile === "healthcare_form") && <SettingCheckbox id="sensitive-cloud-consent" label="Allow sensitive cloud processing" help={HELP.sensitiveCloud} checked={settings.allow_sensitive_cloud} onChange={(allow_sensitive_cloud) => setSettings({ ...settings, allow_sensitive_cloud })} />}
          <button type="button" className="model-refresh" onClick={() => void refreshModels(true)} disabled={modelsLoading}>{modelsLoading ? "Checking Ollama…" : "Refresh local models"}</button>
          {(modelError || (!modelsLoading && !compatibleModels.length)) && <p className="model-warning"><AlertCircle size={14} /> {modelError ?? "No installed model supports both vision and completion. Pull glm-ocr:latest or another vision model, then refresh."}</p>}
          {cloudSelected && <p className="model-warning"><LockKeyhole size={14} /> Adaptive cloud context sends only locally flagged pages. API keys are read from backend environment variables.</p>}
          <SettingField id="input-mode" label="Input mode" help={HELP.inputMode}><select id="input-mode" value={settings.input_mode} onChange={(event) => setSettings({ ...settings, input_mode: event.target.value as ParseSettings["input_mode"] })}><option value="mixed">Mixed PDF</option><option value="scanned">Scanned / image</option><option value="native">Native PDF</option></select></SettingField>
          <SettingField id="render-quality" label="Render quality" help={HELP.dpi}><select id="render-quality" value={settings.dpi} onChange={(event) => setSettings({ ...settings, dpi: Number(event.target.value) as 150 | 200 | 300 })}><option value="150">150 DPI</option><option value="200">200 DPI</option><option value="300">300 DPI</option></select></SettingField>
          <SettingField id="first-page" label="First page" help={HELP.pageRange}><input id="first-page" type="number" min="1" value={settings.start_page} onChange={(event) => setSettings({ ...settings, start_page: Math.max(1, Number(event.target.value)) })} /></SettingField>
          <SettingField id="last-page" label="Last page" help={HELP.pageRange}><input id="last-page" type="number" min={settings.start_page} value={settings.end_page ?? ""} placeholder="All" onChange={(event) => setSettings({ ...settings, end_page: event.target.value ? Number(event.target.value) : null })} /></SettingField>
          <SettingField id="marginalia" label="Marginalia" help={HELP.marginalia}><select id="marginalia" value={settings.marginalia_policy} onChange={(event) => setSettings({ ...settings, marginalia_policy: event.target.value as ParseSettings["marginalia_policy"] })}><option value="remove_repeated">Remove repeated</option><option value="keep_all">Keep all</option></select></SettingField>
          <SettingCheckbox id="describe-figures" label="Describe figures" help={HELP.figures} checked={settings.describe_figures} onChange={(describe_figures) => setSettings({ ...settings, describe_figures })} />
          <p className="required-output-note"><Check size={14} /> Annotated PDF always generated <InfoTip label="Annotated PDF" text={HELP.annotated} /></p>
          <SettingCheckbox id="searchable-pdf" label="Searchable PDF" help={HELP.searchable} checked={settings.searchable_pdf} onChange={(searchable_pdf) => setSettings({ ...settings, searchable_pdf })} />
          <SettingCheckbox id="zip-bundle" label="ZIP bundle" help={HELP.bundle} checked={settings.bundle} onChange={(bundle) => setSettings({ ...settings, bundle })} />
        </section>}

        {!showSettings && !parserAvailable && parserAvailable !== null && <div className="error-banner"><AlertCircle size={18} /><span>{parserError ?? "PaddleOCR-VL Docker runtime is unavailable."}</span></div>}

        {workspaceMode === "schemas" && <SchemaWorkspace onChanged={setExtractionSchemas} />}

        {workspaceMode === "evaluate" && <section className="evaluation-workspace">
          <div className="evaluation-forms">
            <article className="evaluation-card"><span>Single document</span><h2>Evaluate a completed parse</h2><p>Upload a <code>paperplane-ground-truth/v1</code> JSON package.</p><label htmlFor="evaluation-job">Completed job</label><select id="evaluation-job" value={evaluationJobId} onChange={(event) => setEvaluationJobId(event.target.value)}><option value="">Select a completed job</option>{jobs.filter((job) => job.status.startsWith("completed")).map((job) => <option key={job.id} value={job.id}>{job.original_filename}</option>)}</select><label className="file-picker" htmlFor="gold-labels"><Paperclip size={16} /> {goldFile?.name ?? "Choose grounded labels JSON"}</label><input id="gold-labels" hidden type="file" accept="application/json,.json" onChange={(event) => setGoldFile(event.target.files?.[0] ?? null)} /><button className="parse-button" type="button" disabled={evaluationBusy || !evaluationJobId || !goldFile} onClick={() => void runSingleEvaluation()}>{evaluationBusy ? <Loader2 className="spin" size={16} /> : <Check size={16} />} Evaluate output</button></article>
            <article className="evaluation-card"><span>Dataset benchmark</span><h2>Parse and evaluate a batch</h2><p>ZIP with <code>manifest.json</code>, source documents, and grounded labels. Current processing settings apply.</p><label className="file-picker" htmlFor="evaluation-dataset"><UploadCloud size={16} /> {datasetFile?.name ?? "Choose evaluation dataset ZIP"}</label><input id="evaluation-dataset" hidden type="file" accept="application/zip,.zip" onChange={(event) => setDatasetFile(event.target.files?.[0] ?? null)} /><button className="parse-button" type="button" disabled={evaluationBusy || !datasetFile || parserAvailable !== true} onClick={() => void runBatchEvaluation()}>{evaluationBusy ? <Loader2 className="spin" size={16} /> : <Plane size={16} />} Run benchmark</button></article>
          </div>
          <div className="evaluation-results">
            <aside><strong>Evaluation runs</strong>{evaluationRuns.map((run) => <button key={run.id} type="button" className={activeEvaluation?.id === run.id ? "active" : ""} onClick={() => setActiveEvaluation(run)}><span>{run.kind === "batch" ? "Batch benchmark" : run.cases[0]?.external_id ?? "Single evaluation"}</span><small>{statusLabel(run.status)} · {run.completed_cases}/{run.total_cases}</small></button>)}{!evaluationRuns.length && <p>No evaluations yet.</p>}</aside>
            <div className="evaluation-report">{activeEvaluation ? <><div className="evaluation-head"><div><span>{activeEvaluation.kind}</span><h2>{statusLabel(activeEvaluation.status)}</h2></div>{activeEvaluation.report_url && <a className="download-button" href={apiResourceUrl(activeEvaluation.report_url)}><Download size={16} /> Report JSON</a>}</div><div className="metric-grid">{Object.entries(activeEvaluation.metrics ?? {}).map(([name, value]) => <div key={name}><strong>{(value * 100).toFixed(1)}%</strong><span>{name.replaceAll("_", " ")}</span></div>)}</div><div className="case-list">{activeEvaluation.cases.map((item) => <div key={item.id}><span><strong>{item.external_id}</strong><small>{statusLabel(item.status)}{item.error_message ? ` · ${item.error_message}` : ""}</small></span>{item.metrics && <b>{((item.metrics.macro_score ?? 0) * 100).toFixed(1)}%</b>}</div>)}</div></> : <div className="preview-empty"><FileText size={28} /><p>Select or start an evaluation run.</p></div>}</div>
          </div>
        </section>}

        {workspaceMode === "parse" && (pendingFile ? <section className="staging-card">
          <div className="staging-visual"><FileText size={28} /></div>
          <div className="staging-copy"><span>Ready to configure</span><h2>{pendingFiles.length > 1 ? `${pendingFiles.length} documents` : pendingFile.name}</h2><p>{formatBytes(pendingFiles.reduce((sum, file) => sum + file.size, 0))} · Files remain here if backend submission fails.</p>{pendingFiles.length > 1 && <small>{pendingFiles.map((file) => file.name).join(" · ")}</small>}</div>
          <div className="staging-actions">
            <button type="button" className="secondary-button" disabled={busy} onClick={() => inputRef.current?.click()}>Replace</button>
            <button type="button" className="secondary-button" disabled={busy} onClick={removePending}>Remove</button>
            <button type="button" className="parse-button" disabled={busy || parserAvailable !== true} onClick={() => void parsePending()}>{busy ? <Loader2 className="spin" size={17} /> : <Plane size={17} />} Parse {pendingFiles.length > 1 ? "batch" : "document"}</button>
          </div>
          {parserAvailable !== true && <p className="staging-blocked"><AlertCircle size={15} /> {parserAvailable === null ? "Checking PaddleOCR-VL…" : parserError ?? "Prepare the PaddleOCR-VL Docker GPU image."}</p>}
        </section> : !active ? <section className="dropzone">
          <div className="upload-icon"><UploadCloud size={27} /></div><h2>Turn documents into clean Markdown</h2><p>Drop one or many PDFs or images. A batch keeps shared settings and produces a combined ZIP manifest.</p><button onClick={() => inputRef.current?.click()} disabled={busy}>{busy ? <Loader2 className="spin" size={17} /> : <Paperclip size={17} />} Choose documents</button><small>PDF, PNG, JPEG, TIFF · up to 20 files</small>
        </section> : <>
          <section className="file-summary"><div className="file-name"><span><FileText size={21} /></span><div><strong>{active.original_filename}</strong><small>{formatBytes(active.source_size)}</small></div></div><Summary label="Pages" value={String(active.page_count)} /><Summary label="Status" value={statusLabel(active.status)} good={active.status.startsWith("completed")} /><Summary label="Processing time" value={elapsed(active)} />
            <div className="file-actions">
              {(CANCELLABLE.has(active.status) || active.status === "cancelling") && <button type="button" className="stop-button" disabled={stopping} aria-label={stopping ? "Stopping parse" : "Stop parsing"} onClick={() => void stopActive()}>{stopping ? <Loader2 className="spin" size={15} /> : <Square size={14} fill="currentColor" />} {stopping ? "Stopping…" : "Stop"}</button>}
              {markdownArtifact ? <a className="download-button" href={artifactUrl(markdownArtifact)}><Download size={17} /> Download .md</a> : <button className="download-button disabled" disabled><Loader2 className="spin" size={16} /> Preparing</button>}
            </div>
          </section>
          <section className="pipeline"><Stage label="Upload" done /><Stage label="Analyze layout" done={active.status !== "queued" && active.status !== "inspecting"} /><Stage label={`Batch ${active.current_batch ?? Math.min(active.total_batches, Math.floor(active.completed_pages / 10) + 1)}/${active.total_batches} · ${active.completed_pages}/${selectedPageTotal} pages`} done={active.status === "assembling" || active.status.startsWith("completed")} active={active.status === "processing"} /><Stage label="Assemble Markdown + JSON" done={active.status.startsWith("completed")} active={active.status === "assembling"} /></section>
          {active.detected_profile && <div className="required-output-note"><Check size={14} /> Detected profile: {active.detected_profile.replaceAll("_", " ")} ({Math.round((active.profile_confidence ?? 0) * 100)}% confidence){active.is_partial ? " · partial output" : ""}</div>}
          {active.error_message && <div className="error-banner"><AlertCircle size={18} />{active.error_message}</div>}
          {activeBatch && active.batch_id === activeBatch.id && <div className="batch-banner"><strong>Batch {activeBatch.completed_jobs}/{activeBatch.total_jobs} complete</strong><span>{activeBatch.failed_jobs} failed · {activeBatch.cancelled_jobs} cancelled</span>{activeBatch.bundle_ready && activeBatch.bundle_url && <a href={apiResourceUrl(activeBatch.bundle_url)}><Download size={15} /> Download batch ZIP</a>}</div>}
          <DocumentInspector job={active} markdown={markdown} onJobChanged={() => void refresh()} />
          <ArtifactGallery jobId={active.id} artifacts={active.artifacts} />
          <SubDocumentGallery job={active} />
        </>)}
        {error && <div className="toast"><AlertCircle size={18} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError(null)}><X size={16} /></button></div>}
      </section>
    </main>
  );
}

function InfoTip({ label, text }: { label: string; text: string }) {
  const id = useId();
  return <span className="info-tip"><button type="button" aria-label={`About ${label}`} aria-describedby={id}><Info size={13} /></button><span id={id} role="tooltip">{text}</span></span>;
}

function SettingField({ id, label, help, children }: { id: string; label: string; help: string; children: React.ReactNode }) {
  return <div className="setting-field"><span className="setting-label"><label htmlFor={id}>{label}</label><InfoTip label={label} text={help} /></span>{children}</div>;
}

function SettingCheckbox({ id, label, help, checked, onChange }: { id: string; label: string; help: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <div className="setting-check"><label htmlFor={id}><input id={id} type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /> {label}</label><InfoTip label={label} text={help} /></div>;
}

function CloudProviderSelect({ id, label, help, value, providers, onChange }: { id: string; label: string; help: string; value: ParseSettings["review_provider"] | "off"; providers: VisionProvider[]; onChange: (value: ParseSettings["review_provider"] | "off") => void }) {
  return <SettingField id={id} label={label} help={help}><select id={id} value={value} onChange={(event) => onChange(event.target.value as ParseSettings["review_provider"] | "off")}><option value="off">Disabled — local only</option>{providers.filter((provider) => provider.id !== "ollama").map((provider) => <option key={provider.id} value={provider.id} disabled={provider.state !== "ready"}>{provider.name}{provider.state === "ready" ? "" : provider.state === "not_configured" ? " — API key required" : " — unavailable"}</option>)}</select></SettingField>;
}

function ModelSelect({ id, label, help, value, models, loading, onChange }: { id: string; label: string; help: string; value: string | null; models: VisionModel[]; loading: boolean; onChange: (value: string | null) => void }) {
  return <SettingField id={id} label={label} help={help}><select id={id} value={value ?? ""} disabled={loading} onChange={(event) => onChange(event.target.value || null)}><option value="">{loading ? "Loading local models…" : "Select a model"}</option>{models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}</select></SettingField>;
}

function Summary({ label, value, good = false }: { label: string; value: string; good?: boolean }) {
  return <div className="summary-item"><strong className={good ? "good" : ""}>{value}</strong><small>{label}</small></div>;
}

function Stage({ label, done = false, active = false }: { label: string; done?: boolean; active?: boolean }) {
  return <div className={`stage ${done ? "done" : ""} ${active ? "current" : ""}`}><i>{done ? <Check size={13} /> : active ? <Loader2 className="spin" size={13} /> : null}</i><span>{label}</span></div>;
}
