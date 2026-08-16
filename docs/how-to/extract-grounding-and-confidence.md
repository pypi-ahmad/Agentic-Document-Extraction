# How to extract grounding and confidence from a parse result

**Goal:** given a Paperplane `ParseResponse` (or its exported JSON), pull the
normalized box and Markdown range for a block, and tell whether a word's
confidence is raw or calibrated.

This assumes you are working in Python against Paperplane's internal objects
(`paperplane.contracts`, `paperplane.ade_contracts`), not just the exported
JSON files. If you only have the downloaded JSON, skip to
[From exported JSON](#from-exported-json) below.

## From a `ParseResponse` object

```python
from paperplane.contracts import ParseResponse

def block_grounding(response: ParseResponse, block_id: str) -> None:
    def walk(node):
        if node.id == block_id:
            return node
        for child in node.children:
            found = walk(child)
            if found is not None:
                return found
        return None

    node = walk(response.structure)
    if node is None or node.box is None:
        raise ValueError(f"{block_id} has no grounding box")

    box = node.box  # NormalizedBox: left, top, right, bottom in [0, 1]
    text = "".join(response.markdown[r.start : r.end] for r in node.ranges)
    print(box, text)
```

`node.box` and `node.ranges` are populated only when
`node.grounding_status == "grounded"`; a `"semantic_only"` node (see
`paperplane/contracts.py:33` and `:128-131`) has Markdown ranges but no box —
check `grounding_status` before assuming a box exists.

## Distinguishing raw vs. calibrated confidence

Word-level confidence lives on `GroundedWord.raw_confidence`
(`paperplane/contracts.py:91-99`) for native/OCR-observed words. To classify it
as raw or calibrated, run it through `calibration.confidence_for`:

```python
from paperplane.calibration import confidence_for, CalibrationProfile

result = confidence_for(
    word.raw_confidence,
    engine=response.metadata.engine,
    model=response.metadata.model,
    version="paperplane-5.0.0",
    profile=my_loaded_profile,  # CalibrationProfile | None
)

print(result.label)       # "raw (uncalibrated)" or "calibrated"
print(result.calibrated)  # None unless the profile matched exactly
```

`confidence_for` only returns a calibrated score when `profile.engine`,
`profile.model`, and `profile.version` match the response's engine/model/version
*exactly* (`paperplane/calibration.py:45-51`). Any mismatch — including a minor
version bump — silently falls back to `"raw (uncalibrated)"`. This function is
defined in the codebase but is not wired into the default v5 export path (see
[Reference: ADE JSON schema](../reference/ade-json-schema.md#confidence_kind));
call it yourself if you need a calibrated score.

## From exported JSON

If you only have the downloaded `.json` files (no Python objects), the same
information is available without importing Paperplane:

```python
import json

with open("result.v5.json") as f:
    v5 = json.load(f)

markdown = v5["ade"]["markdown"]

for word in v5["words"]:
    start, end = word["grounding"]["range"]["start"], word["grounding"]["range"]["end"]
    assert markdown[start:end] == word["text"]
    print(word["text"], word["grounding"]["box"], word["confidence_kind"])
```

Every `confidence_kind` in a freshly downloaded v5 export will read
`"raw_uncalibrated"` unless you generated the result with an active,
exactly-matching `CalibrationProfile` — see
[Reference: ADE JSON schema](../reference/ade-json-schema.md) for the full field
list.
