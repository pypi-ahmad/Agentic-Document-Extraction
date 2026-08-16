# Tutorial: read the JSON output

This tutorial walks you through parsing a document and finding the same piece of
grounded text in both JSON exports Paperplane produces: the **ADE v2-style**
export and the richer **Paperplane v5** export. By the end you will be able to
point to one specific field in each file and explain what it means.

You need a running Paperplane instance. If you have not set one up yet, follow
[Setup](../SETUP.md) first.

## 1. Parse a sample document

1. Start Paperplane and open [http://127.0.0.1:8551](http://127.0.0.1:8551).
2. On **Parse**, activate the **Docling ADE** engine toggle (no API key required).
3. Upload `Sample-PDF/PublicWaterMassMailing.pdf` from the repository root.
4. Leave the default page range and select **Parse files**.
5. Wait for the progress bar to reach 100%.

## 2. Open both JSON exports

1. Once parsing finishes, use the shared document selector to open the **JSON**
   tab.
2. The tab switches between the strict **ADE v2-style** export and the richer
   **Paperplane v5** export — select the ADE v2-style view first and download it.
3. Switch the selector to the Paperplane v5 view and download that file too.

You now have two files, e.g. `result.ade.json` and `result.v5.json`, describing
the same parsed document.

## 3. Find one grounded text block

Open the ADE v2 JSON file. Its top level has three keys:

```json
{
  "markdown": "...",
  "metadata": { "...": "..." },
  "structure": { "id": "document-0", "type": "document", "children": [ ... ] }
}
```

1. Walk into `structure.children[0]` — this is the first `page` node.
2. Walk into its own `children[0]` — this is the first content block (commonly a
   `title` or `text` node with an `id` like `"text-0"`).
3. Read its `grounding` object:
   ```json
   "grounding": {
     "page": 1,
     "range": { "start": 0, "end": 42 },
     "box": { "xmin": 0.08, "ymin": 0.05, "xmax": 0.9, "ymax": 0.12 }
   }
   ```
   `range.start`/`range.end` are Unicode code-point offsets into the top-level
   `markdown` string. Slice `markdown[range.start:range.end]` and it will equal
   that block's visible text exactly — Paperplane guarantees this alignment
   (`paperplane/contracts.py:255-257`, `paperplane/ade_contracts.py:143-146`).
   `box` is a normalized `[0, 1]` bounding box on the page image.

## 4. Find the same block's confidence in the v5 JSON

The Paperplane v5 export wraps the same ADE-shaped structure and adds a flat
`words` list of individually observed words:

```json
{
  "contract": "paperplane.parse.v5",
  "ade": { "...": "the same ADE v2 structure as step 3" },
  "engine": "docling",
  "words": [
    {
      "text": "Public",
      "grounding": { "page": 1, "range": { "start": 0, "end": 6 }, "box": { "...": "..." } },
      "confidence": 0.94,
      "confidence_kind": "raw_uncalibrated"
    }
  ],
  "relations": [],
  "warnings": []
}
```

1. Find a word in `words` whose `grounding.range` falls inside the block range
   you read in step 3.
2. Check its `confidence_kind`. On a fresh checkout this is always
   `"raw_uncalibrated"` — Paperplane only reports `"calibrated"` when a
   version- and corpus-pinned calibration profile exists for the exact engine,
   model, and version that produced the result
   (`paperplane/calibration.py:37-51`).

**You're done when:** you can point to one block's `grounding.range` in the ADE
v2 JSON, show that `markdown[start:end]` matches its text, and name the
`confidence_kind` of a word inside that same range in the v5 JSON.

Next: see [How to extract grounding and confidence](../how-to/extract-grounding-and-confidence.md)
to do this in Python instead of by hand.
