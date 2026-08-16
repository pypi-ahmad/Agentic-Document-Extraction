# Tutorial: organize a document

This tutorial walks through the full **Organize** workflow — Classify, then Split, then
Section — on a document you have already parsed. By the end you will have downloaded a
`sections.json` file and understand what each Organize tab produced and why.

Organize never re-parses your file. It only reads the Markdown, structure, and grounding
already produced by Parse, so everything you do here is fast, local, and repeatable.

## Prerequisites

- Paperplane running at [http://127.0.0.1:8551](http://127.0.0.1:8551).
- At least one document already parsed on the **Parse** page. Any engine works — Organize
  only needs the resulting Markdown and structure, not the original file.

If you have not parsed anything yet, do that first: open **Parse**, activate one engine,
upload a document (the bundled `Sample-PDF/` works), and select **Parse files**.

## Step 1: open Organize and pick your document

1. Open the **Organize** page from the sidebar.
2. Use the **Parsed document** selector at the top to choose the document you parsed
   earlier. Organize lists every document from your current session that finished parsing.

If nothing appears here, Organize shows "Parse at least one document first" and stops —
go back to Parse.

## Step 2: classify pages

The **Classify** tab assigns every page of your document to one of a list of class names
you provide.

1. In the **Allowed classes** box, keep the default list or replace it with names relevant
   to your document, one per line:
   ```
   invoice
   letter
   report
   ```
2. Select **Classify pages**.
3. Read the JSON result. Each entry under `pages` has a `page` number, the assigned
   `label`, a `reason` (which keyword matched, or a note that none did), and the grounded
   `ranges` into the document's Markdown.

Classification here is a **deterministic keyword match**, not a model call: a page gets a
label the first time one of that class's name/description terms (longer than three
characters) appears in the page's text (`paperplane/ade_workflows.py:70-79`). If no class
matches, the page is assigned the *first* class in your list, and a warning is added.
See [Tune Classify classes](../how-to/tune-classify-classes.md) if labels look wrong.

## Step 3: split into sub-documents

The **Split** tab groups pages by the same classes, then hands you back one Markdown
document per label.

1. In the **Split classes** box, use the same (or a different) class list.
2. Select **Split document**.
3. Read the JSON result. Each entry under `documents` has a `label`, the list of `pages`
   that were grouped together, and a `markdown` string containing those pages joined with
   an `<!-- PAGE BREAK -->` comment between them (`paperplane/ade_workflows.py:126-146`).

Split always runs Classify internally first, using the same class list you gave it, so any
classification warnings from Step 2 carry over into the split result's `warnings` field.

## Step 4: detect sections

The **Section** tab does not use your class list at all — it looks for a heading-like block
at the start of each page.

1. Select **Detect sections**.
2. Read the JSON result. Each entry under `sections` has a `title`, a `section_number`, the
   `page` it starts on, a `start_reference` (the grounded block ID the title came from), and
   its `ranges`.
3. Select **Download section map** to save the result as `sections.json`.

If a page's first grounded block is not marked as a title or heading, Paperplane still uses
it as the section title and adds a warning noting that the result is a partial
(`paperplane/ade_workflows.py:109-112`).

## What you should have now

- A classification of every page into one of your chosen classes, with a reason for each.
- One Markdown sub-document per class label.
- A downloaded `sections.json` file listing every detected section with its grounded start
  reference.

Every result you produced traces back to specific page and character ranges in your
original Parse output — nothing here was re-inferred by a model. See
[why Organize is deterministic](../explanation/why-organize-is-deterministic.md) for the
reasoning behind that design, or [the schema reference](../reference/organize-schemas.md)
for the exact shape of every field you just saw.
