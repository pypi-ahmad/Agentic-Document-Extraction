# Evidence Studio Design

## Goal

Turn Paperplane into a compact, document-first extraction studio inspired by the strongest workflow patterns observed in Landing AI ADE and LlamaIndex Cloud without copying either product's visual identity or adding backend scope.

## Product Direction

The selected direction is **Evidence Studio** with the **Graphite Signal** visual system. The application becomes a full-height working environment instead of a marketing-style landing page:

- a compact header preserves the Paperplane identity, model chain, and theme switch;
- a slim tool rail exposes the primary new-extraction and run-history actions;
- persistent run history keeps status and progress visible;
- a center canvas prioritizes the source or annotated document;
- a right workspace switches between Configure, Results, and Evaluate.

Dark remains the default. Graphite and near-black surfaces carry the interface, violet identifies interactive selection, and green, amber, and red remain reserved for success, warning, and failure. The light theme provides equivalent hierarchy and contrast.

## Workflow

The initial empty state opens Configure. Selecting a local PDF or image creates a temporary browser preview without uploading it. Starting extraction preserves that preview for the newly created job during the current browser session and switches the workspace to Results.

Selecting a historical run opens Results. A completed run uses its annotated PDF as the document preview when present. Because this redesign is frontend-only, historical runs without an annotated PDF show a clear unavailable, processing, or failure state instead of requesting a new source-file endpoint.

Results show status, page progress, cache reuse, output tokens, estimated cost, and generated artifacts. Text and JSON artifacts can be previewed in the workspace; JSON is formatted when valid. Downloads remain available even when preview loading fails or a file type is download-only. Evaluate keeps the existing ground-truth upload and score flow in a dedicated tab for terminal runs.

## Architecture

The home page remains the data and command owner for jobs, polling, configuration, cancellation, evaluation, theme state, and active workspace tab. Presentation is split into focused V2 components:

- `RunHistory` renders run selection and status only.
- `DocumentCanvas` renders local or artifact-backed PDF/image previews and their empty/error states.
- `ArtifactPreview` owns text/JSON artifact fetching, formatting, download fallback, and loading errors.

Temporary object URLs are revoked when replaced or when the page unmounts. Artifact fetches use `AbortController` and ignore aborted results. No new package, API route, database field, or deployment setting is introduced.

## Responsive and Accessible Behavior

The multi-pane layout is optimized for desktop. At tablet widths the run history collapses into a horizontal strip; at mobile widths the viewer and workspace stack, controls remain reachable, and no content requires horizontal page scrolling.

Native buttons, tabs, inputs, and links retain keyboard interaction. Tabs expose `tablist`, `tab`, and `tabpanel` semantics; selected runs expose current state; icon-only controls have accessible names; focus indicators remain visible in both themes. Status is communicated with text in addition to color.

## Failure Handling

- Backend connection failures remain a prominent actionable alert.
- Missing document previews explain why the file cannot be displayed.
- Failed artifact previews keep the download action available.
- Invalid JSON is shown as original text rather than discarded.
- Storage failures do not prevent in-page theme switching.
- Failed or cancelled jobs remain selectable and expose their backend error message.

## Verification

- Component tests cover configuration and submission, workspace tab changes, session preview lifecycle, historical preview fallback, artifact text/JSON loading and failure, run switching, cancellation, evaluation, and theme persistence.
- TypeScript, ESLint, Vitest, and the Next.js production build pass.
- The existing backend and launcher tests pass unchanged.
- Playwright CLI checks dark and light desktop layouts plus the collapsed mobile layout using empty, processing, completed, and failed states.
