# How to tune Classify classes

**Goal:** get Classify and Split to assign the labels you expect, instead of everything
falling through to the first class in your list.

## Understand the matching rule first

Classify does not use a model. For each page, it walks your class list *in order* and picks
the first class whose name or description contains a word — longer than three characters —
that also appears somewhere in that page's text. If no class matches at all, the page gets
the *first* class in your list and a warning (`paperplane/ade_workflows.py:70-79`):

```python
def _class_for_text(text: str, classes: list[ClassDefinition]) -> tuple[str, str]:
    normalized = text.casefold()
    for candidate in classes:
        terms = set(
            re.findall(r"[a-z0-9]+", f"{candidate.name} {candidate.description}".casefold())
        )
        hits = sorted(term for term in terms if len(term) > 3 and term in normalized)
        if hits:
            return candidate.name, f"Matched source term: {hits[0]}"
    return classes[0].name, "No deterministic keyword match; returned the first allowed class"
```

Three consequences follow directly from this:

1. **Order matters.** The first class in your list that has any matching term wins, even if
   a later class would have been a better fit. Put your most specific classes first.
2. **Short words are ignored.** Only terms longer than three characters count, so a class
   named `"1099"` will never self-match by name (it has no run of letters that long) — give
   it a description with a real keyword instead.
3. **No match is not an error.** A page that matches nothing silently becomes the first
   class in your list, with a warning buried in the response's `warnings` array. Always
   check `warnings` before trusting a classification result.

## In the Organize UI

The **Classify** and **Split** tabs in `app_pages/organize.py` build one `ClassDefinition`
per line of text you enter, and — in the UI only — set the description equal to the name
(`app_pages/organize.py:48-50`):

```python
def classes_from_text(value: str) -> list[ClassDefinition]:
    names = [item.strip() for item in value.splitlines() if item.strip()]
    return [ClassDefinition(name=name, description=name) for name in names]
```

This means the UI has no separate description field — the class *name itself* is the only
source of matching keywords. So in the UI, tune classes by:

- **Using distinctive, multi-word-safe names.** `purchase-order` beats `order` if your
  documents also mention "work order" or "restraining order".
- **Avoiding near-duplicate names.** `invoice` and `invoicing` both tokenize similarly and
  will fight for the same pages — pick one.
- **Ordering from most specific to most general.** If `credit-note` and `invoice` could both
  match a page, put `credit-note` first.
- **Adding a deliberate catch-all first only if you want a default,** since the *first*
  class is both "most likely to be tried first" and "the fallback on no match" — those are
  in tension. If you want a real default bucket, put a generic class like `other` *last* in
  your reading order but understand it will still be the fallback for zero-match pages
  regardless of position, per the code above (`classes[0]`, not the semantically-generic
  one).

## Calling `classify_document` directly

If you drive Organize programmatically rather than through the UI, you get the full
`ClassDefinition(name=..., description=...)` model, so you can put your real keywords in
`description` and keep `name` short and clean for display:

```python
from paperplane.ade_workflows import ClassDefinition, classify_document

classes = [
    ClassDefinition(name="invoice", description="invoice billing amount due remittance"),
    ClassDefinition(name="letter", description="dear sincerely regards correspondence"),
]
result = classify_document(parsed, classes)
```

This lets you pack several matching keywords into one class without cluttering the label
shown to users.

## Diagnosing an unexpected label

1. Open the classification result's `pages` list and find the page.
2. Read its `reason` field. `"Matched source term: <word>"` tells you exactly which keyword
   fired and from which class. `"No deterministic keyword match..."` tells you it fell
   through to the first class.
3. If the match is unexpected, check whether an *earlier* class in your list also contains
   that keyword — the first hit wins, so an earlier, broader class can shadow a more
   specific one later in the list.
4. If nothing matched, add a keyword from the page's own text (visible in the parsed
   Markdown or Output tab) to the relevant class's name or description.
