"""v0.5.0 metric suite.

The v0.4.0 suite (`app.services.eval.metrics`) covers
per-field F1, schema conformance, ANLS, ECE, Brier, AUROC,
and coverage-at-target-accuracy. The v0.5.0 suite adds:

**Tables:**
* :func:`teds` — Tree-Edit-Distance Similarity (Zhong et al., 2019)
* :func:`cell_precision_recall_f1` — per-cell value match
* :func:`row_column_structure_accuracy` — topology-only accuracy
* :func:`header_match_accuracy` — column-name match

**Key-value:**
* :func:`exact_match` — strict string equality
* :func:`token_f1` — SQuAD-style token F1
* :func:`anls` — already in v0.4.0; re-exported here for the v2
  suite

**Document grounding:**
* :func:`evidence_attribution_accuracy` — fraction of fields
  with valid evidence (non-empty text_span)
* :func:`bbox_iou` — mean IoU between extracted and gold bboxes
* :func:`page_localization_accuracy` — fraction of fields where
  the extracted page matches the gold page

**Production metric:**
* :func:`end_to_end_task_success_rate` — per-schema all-or-nothing

All metrics are pure functions: no I/O, no global state, no
model calls. They take ``predictions`` and ``references`` and
return a float or a dict of floats.

This module is intentionally independent of the v0.4.0
``metrics`` module so the two suites can be used together or
separately.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# ── Tokenization helpers ──────────────────────────────────────────


def _tokens(text: str) -> list[str]:
    """Lowercase, whitespace-split tokens for the EM/token-F1 metrics."""

    return [t for t in (text or "").lower().split() if t]


# ── Exact Match ─────────────────────────────────────────────────


def exact_match(predicted: str, expected: str) -> float:
    """Strict string equality. Returns 1.0 if equal, 0.0 otherwise.

    Normalizes whitespace before comparison.
    """

    if predicted is None or expected is None:
        return 0.0
    return 1.0 if " ".join(predicted.split()) == " ".join(expected.split()) else 0.0


def exact_match_batch(
    predictions: Sequence[Any],
    references: Sequence[Any],
) -> float:
    """Mean EM across a batch of (prediction, reference) pairs."""

    if not predictions or not references:
        return 0.0
    n = min(len(predictions), len(references))
    if n == 0:
        return 0.0
    total = 0.0
    for p, r in zip(predictions[:n], references[:n], strict=False):
        total += exact_match(str(p), str(r))
    return total / n


# ── Token F1 (SQuAD) ────────────────────────────────────────────


def token_f1(predicted: str, expected: str) -> float:
    """SQuAD-style token F1: harmonic mean of token precision/recall."""

    pred_tokens = _tokens(predicted)
    ref_tokens = _tokens(expected)
    if not pred_tokens and not ref_tokens:
        return 1.0
    if not pred_tokens or not ref_tokens:
        return 0.0
    common: dict[str, int] = {}
    for t in pred_tokens:
        common[t] = min(pred_tokens.count(t), ref_tokens.count(t))
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    precision = num_same / len(pred_tokens)
    recall = num_same / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def token_f1_batch(
    predictions: Sequence[Any],
    references: Sequence[Any],
) -> float:
    """Mean token F1 across a batch."""

    if not predictions or not references:
        return 0.0
    n = min(len(predictions), len(references))
    if n == 0:
        return 0.0
    total = 0.0
    for p, r in zip(predictions[:n], references[:n], strict=False):
        total += token_f1(str(p), str(r))
    return total / n


# ── TEDS (Tree-Edit-Distance Similarity) ─────────────────────────


def _table_to_tree(table: list[list[str]]) -> tuple[Any, ...]:
    """Convert a 2-D table to a tuple tree for the TEDS algorithm.

    Internal nodes carry a structural label (``"table"`` /
    ``"row"``) and a children tuple. Leaf nodes are
    ``(value, ())`` so the value (not the structural tag) is
    the node's label. The tree for ``[["A", "B"], ["1", "2"]]``
    is:

    .. code-block:: text

        ("table", (
            ("row", (
                ("A", ()),
                ("B", ()),
            )),
            ("row", (
                ("1", ()),
                ("2", ()),
            )),
        ))
    """

    rows: list[tuple[Any, ...]] = []
    for row in table:
        cells: list[tuple[Any, ...]] = []
        for cell in row or [""]:
            value = str(cell).strip().lower()
            cells.append((value, ()))
        rows.append(("row", tuple(cells)))
    return ("table", tuple(rows))


def _ted(tree1: tuple, tree2: tuple) -> int:
    """Zhang-Shasha tree edit distance.

    A direct port of the classic algorithm: O(n^2) for two
    trees of size n. We use a simple post-order traversal
    followed by the standard dynamic-programming table. This is
    good enough for small tables (a few hundred cells). For
    very large tables the user should swap in APTED.

    Leaf nodes ``("cell", value)`` match iff the value is
    identical (case-insensitive). Internal nodes match iff
    their structural label matches.
    """

    def _label(node: tuple) -> str:
        """The label used for comparison: the cell value for leaves,
        the structural tag (``row``, ``table``) for internal nodes."""

        if len(node) >= 2 and isinstance(node[1], tuple):
            return str(node[0])
        return str(node)

    def _postorder(tree: tuple) -> list[tuple]:
        out: list[tuple] = []
        if isinstance(tree, tuple) and len(tree) >= 2 and isinstance(tree[1], tuple):
            label = _label(tree)
            children = tree[1]
            child_indices: list[int] = []
            for child in children:
                child_indices.append(len(out))
                _postorder_recursive(child, out)
            out.append((label, tuple(child_indices)))
        else:
            out.append(tree)
        return out

    def _postorder_recursive(tree: tuple, out: list[tuple]) -> None:
        if isinstance(tree, tuple) and len(tree) >= 2 and isinstance(tree[1], tuple):
            label = _label(tree)
            children = tree[1]
            child_indices: list[int] = []
            for child in children:
                child_indices.append(len(out))
                _postorder_recursive(child, out)
            out.append((label, tuple(child_indices)))
        else:
            out.append(tree)

    t1 = _postorder(tree1)
    t2 = _postorder(tree2)
    n = len(t1)
    m = len(t2)
    # Label matching: a delete-then-insert costs 2; a relabel costs 1.
    # We treat all leaf cells as having a "string" label that
    # matches only if equal.
    td: list[list[int]] = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        td[i][0] = i
    for j in range(m + 1):
        td[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            l1, _ = t1[i - 1]
            l2, _ = t2[j - 1]
            cost = 0 if l1 == l2 else 1
            td[i][j] = min(
                td[i - 1][j] + 1,  # delete
                td[i][j - 1] + 1,  # insert
                td[i - 1][j - 1] + cost,  # match/relabel
            )
    return td[n][m]


def teds(predicted: list[list[str]], expected: list[list[str]]) -> float:
    """Tree-Edit-Distance Similarity between two 2-D tables.

    Returns a value in [0, 1]: 1.0 means the two trees are
    isomorphic, 0.0 means maximally different. The denominator
    is the sum of the two tree sizes; an empty table on both
    sides returns 1.0.
    """

    t1 = _table_to_tree(predicted or [[]])
    t2 = _table_to_tree(expected or [[]])
    # Special case: both empty
    if (not predicted or all(not r for r in predicted)) and (
        not expected or all(not r for r in expected)
    ):
        return 1.0
    dist = _ted(t1, t2)
    size1 = _tree_size(t1)
    size2 = _tree_size(t2)
    denom = size1 + size2
    if denom == 0:
        return 1.0
    return max(0.0, 1.0 - dist / denom)


def _tree_size(tree: tuple) -> int:
    if isinstance(tree, tuple) and len(tree) >= 2 and isinstance(tree[1], tuple):
        return 1 + sum(_tree_size(child) for child in tree[1])
    return 1


# ── Cell-level Precision/Recall/F1 ──────────────────────────────


def _normalize_cell(value: Any) -> str:
    """Normalize a cell value for comparison."""

    if value is None:
        return ""
    return " ".join(str(value).split()).strip().lower()


def _to_grid(table: Any) -> list[list[str]]:
    """Coerce a table to a 2-D list of strings."""

    if table is None:
        return []
    if isinstance(table, list):
        rows: list[list[str]] = []
        for row in table:
            if isinstance(row, list):
                rows.append([_normalize_cell(c) for c in row])
            elif isinstance(row, dict):
                rows.append([_normalize_cell(v) for v in row.values()])
            else:
                rows.append([_normalize_cell(row)])
        return rows
    return [[_normalize_cell(table)]]


def cell_precision_recall_f1(
    predicted: Any,
    expected: Any,
    *,
    numeric_tol: float = 1e-6,
) -> dict[str, float]:
    """Per-cell P/R/F1 between two 2-D tables.

    Cells are matched positionally. Numeric cells (parsed as
    float) are compared with a tolerance; non-numeric cells
    are compared as normalized strings. Cells outside the
    shorter table are counted as deletions (FN) or insertions
    (FP).
    """

    p = _to_grid(predicted)
    e = _to_grid(expected)
    n_p = sum(len(r) for r in p)
    n_e = sum(len(r) for r in e)
    if n_p == 0 and n_e == 0:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if n_p == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    if n_e == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    tp = 0
    for i in range(max(len(p), len(e))):
        p_row = p[i] if i < len(p) else []
        e_row = e[i] if i < len(e) else []
        for j in range(max(len(p_row), len(e_row))):
            pc = p_row[j] if j < len(p_row) else None
            ec = e_row[j] if j < len(e_row) else None
            if _cells_match(pc, ec, numeric_tol):
                tp += 1
    precision = tp / n_p
    recall = tp / n_e
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _cells_match(a: str | None, b: str | None, numeric_tol: float) -> bool:
    if a is None or b is None:
        return False
    if a == b:
        return True
    # Try numeric comparison
    try:
        af = float(a.replace(",", ""))
        bf = float(b.replace(",", ""))
        return abs(af - bf) < numeric_tol
    except (TypeError, ValueError):
        return False


# ── Row/Column structure accuracy ───────────────────────────────


def row_column_structure_accuracy(predicted: Any, expected: Any) -> dict[str, float]:
    """Topology-only accuracy: do the row/column counts match?

    Both metrics return 1.0 if the predicted and expected
    tables have the same number of rows / columns. Header
    rows are counted in both.
    """

    p = _to_grid(predicted)
    e = _to_grid(expected)
    n_rows_p = len(p)
    n_rows_e = len(e)
    n_cols_p = max((len(r) for r in p), default=0)
    n_cols_e = max((len(r) for r in e), default=0)
    return {
        "row_accuracy": 1.0 if n_rows_p == n_rows_e else 0.0,
        "column_accuracy": 1.0 if n_cols_p == n_cols_e else 0.0,
    }


# ── Header match accuracy ───────────────────────────────────────


def header_match_accuracy(predicted: Any, expected: Any) -> float:
    """Fraction of predicted header cells that match the gold header.

    Header is the first row. Empty strings count as 0 matches
    but do not crash the comparison.
    """

    p = _to_grid(predicted)
    e = _to_grid(expected)
    if not p and not e:
        return 1.0
    if not p or not e:
        return 0.0
    p_header = p[0]
    e_header = e[0]
    if not p_header and not e_header:
        return 1.0
    if not p_header or not e_header:
        return 0.0
    n = max(len(p_header), len(e_header))
    matches = sum(
        1
        for i in range(n)
        if i < len(p_header) and i < len(e_header) and p_header[i] == e_header[i]
    )
    return matches / n


# ── Evidence attribution accuracy ──────────────────────────────


def evidence_attribution_accuracy(
    evidences: Mapping[str, Any],
) -> float:
    """Fraction of fields with valid evidence (non-empty text_span).

    Each value of ``evidences`` may be an :class:`Evidence`
    (dataclass) or a dict with a ``text_span`` key.
    """

    if not evidences:
        return 0.0
    covered = 0
    for ev in evidences.values():
        span = _get_span(ev)
        if span and str(span).strip():
            covered += 1
    return covered / len(evidences)


def _get_span(ev: Any) -> Any:
    if hasattr(ev, "text_span"):
        return ev.text_span
    if isinstance(ev, dict):
        return ev.get("text_span")
    return None


# ── Bbox IoU (mean) ────────────────────────────────────────────


def bbox_iou(
    a: tuple[float, float, float, float] | None,
    b: tuple[float, float, float, float] | None,
) -> float:
    """IoU between two bboxes. None / degenerate boxes return 0.0."""

    if a is None or b is None:
        return 0.0
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    if ax1 <= ax0 or ay1 <= ay0 or bx1 <= bx0 or by1 <= by0:
        return 0.0
    inter_x0 = max(ax0, bx0)
    inter_y0 = max(ay0, by0)
    inter_x1 = min(ax1, bx1)
    inter_y1 = min(ay1, by1)
    if inter_x1 <= inter_x0 or inter_y1 <= inter_y0:
        return 0.0
    inter = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
    area_a = (ax1 - ax0) * (ay1 - ay0)
    area_b = (bx1 - bx0) * (by1 - by0)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return float(inter / union)


def mean_bbox_iou(
    predicted: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> float:
    """Mean IoU across fields that appear in both ``predicted`` and ``expected``.

    Fields missing from either side contribute 0.0. Fields
    where either side has no bbox contribute 0.0.
    """

    common = set(predicted) & set(expected)
    if not common:
        return 0.0
    total = 0.0
    for fname in common:
        pb = _get_bbox(predicted[fname])
        eb = _get_bbox(expected[fname])
        total += bbox_iou(pb, eb)
    return total / len(common)


def _get_bbox(ev: Any) -> tuple[float, float, float, float] | None:
    if hasattr(ev, "bbox"):
        bbox = ev.bbox
    elif isinstance(ev, dict):
        bbox = ev.get("bbox")
    else:
        return None
    if bbox is None:
        return None
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        try:
            return tuple(float(x) for x in bbox)  # type: ignore[return-value]
        except (TypeError, ValueError):
            return None
    return None


# ── Page localization accuracy ──────────────────────────────────


def page_localization_accuracy(
    predicted: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> float:
    """Fraction of fields where the extracted page matches the gold page.

    Fields missing from either side contribute 0.0.
    """

    common = set(predicted) & set(expected)
    if not common:
        return 0.0
    matches = 0
    for fname in common:
        pp = _get_page(predicted[fname])
        ep = _get_page(expected[fname])
        if pp is not None and ep is not None and int(pp) == int(ep):
            matches += 1
    return matches / len(common)


def _get_page(ev: Any) -> int | None:
    if hasattr(ev, "page"):
        return ev.page
    if isinstance(ev, dict):
        return ev.get("page")
    return None


# ── End-to-end task success rate ────────────────────────────────


def end_to_end_task_success_rate(
    predictions: Sequence[Mapping[str, Any]],
    references: Sequence[Mapping[str, Any]],
    *,
    case_insensitive: bool = True,
) -> float:
    """Fraction of documents where EVERY field matches the reference.

    A document's "success" is computed by iterating over the
    reference's keys; each value is compared to the prediction
    via ``token_f1`` and is considered a pass if F1 >= 0.999
    (i.e. token-exact match).
    """

    if not predictions or not references:
        return 0.0
    n = min(len(predictions), len(references))
    if n == 0:
        return 0.0
    successes = 0
    for pred, ref in zip(predictions[:n], references[:n], strict=False):
        if _doc_success(pred, ref, case_insensitive=case_insensitive):
            successes += 1
    return successes / n


def _doc_success(
    pred: Mapping[str, Any], ref: Mapping[str, Any], *, case_insensitive: bool
) -> bool:
    if not ref:
        return not pred  # empty ref is matched by empty pred
    for key, expected in ref.items():
        # Skip meta blocks
        if isinstance(key, str) and key.startswith("_"):
            continue
        pv = pred.get(key)
        if pv is None and expected is None:
            continue
        if pv is None or expected is None:
            return False
        if case_insensitive and isinstance(pv, str) and isinstance(expected, str):
            pv = pv.lower()
            expected = expected.lower()
        if isinstance(pv, str) and isinstance(expected, str):
            if token_f1(pv, expected) < 0.999:
                return False
        elif isinstance(pv, (int, float)) and isinstance(expected, (int, float)):
            if abs(float(pv) - float(expected)) > 1e-6:
                return False
        elif isinstance(pv, list) and isinstance(expected, list):
            if len(pv) != len(expected):
                return False
        elif isinstance(pv, dict) and isinstance(expected, dict):
            if not _doc_success(pv, expected, case_insensitive=case_insensitive):
                return False
        else:
            if str(pv) != str(expected):
                return False
    return True


# ── Re-export the v0.4.0 ANLS for the v2 suite ─────────────────


def anls(predicted: str, expected: str, threshold: float = 0.5) -> float:
    """Re-exported from v0.4.0 metrics for the v2 suite."""

    from app.services.eval.metrics import anls as _anls  # local import to avoid cycle

    return _anls(predicted, expected, threshold=threshold)


# ── Full-suite runner ───────────────────────────────────────────


def run_v2_suite(
    *,
    predictions_kv: Sequence[Any] | None = None,
    references_kv: Sequence[Any] | None = None,
    predictions_table: Sequence[Any] | None = None,
    references_table: Sequence[Any] | None = None,
    predicted_evidences: Mapping[str, Any] | None = None,
    expected_evidences: Mapping[str, Any] | None = None,
    e2e_predictions: Sequence[Mapping[str, Any]] | None = None,
    e2e_references: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, float]:
    """Run the full v0.5.0 metric suite and return a flat dict.

    Any of the inputs can be ``None``; the corresponding
    metrics are simply omitted from the output.
    """

    out: dict[str, float] = {}
    if predictions_kv is not None and references_kv is not None:
        out["em"] = exact_match_batch(predictions_kv, references_kv)
        out["token_f1"] = token_f1_batch(predictions_kv, references_kv)
    if predictions_table is not None and references_table is not None:
        teds_scores = [
            teds(p, r) for p, r in zip(predictions_table, references_table, strict=False)
        ]
        out["teds"] = sum(teds_scores) / max(1, len(teds_scores))
        cell_f1s = [
            cell_precision_recall_f1(p, r)["f1"]
            for p, r in zip(predictions_table, references_table, strict=False)
        ]
        out["cell_f1"] = sum(cell_f1s) / max(1, len(cell_f1s))
        header_scores = [
            header_match_accuracy(p, r)
            for p, r in zip(predictions_table, references_table, strict=False)
        ]
        out["header_match_accuracy"] = sum(header_scores) / max(1, len(header_scores))
        row_col_scores = [
            row_column_structure_accuracy(p, r)
            for p, r in zip(predictions_table, references_table, strict=False)
        ]
        if row_col_scores:
            out["row_accuracy"] = sum(s["row_accuracy"] for s in row_col_scores) / len(
                row_col_scores
            )
            out["column_accuracy"] = sum(s["column_accuracy"] for s in row_col_scores) / len(
                row_col_scores
            )
    if predicted_evidences is not None:
        out["evidence_attribution_accuracy"] = evidence_attribution_accuracy(predicted_evidences)
    if predicted_evidences is not None and expected_evidences is not None:
        out["mean_bbox_iou"] = mean_bbox_iou(predicted_evidences, expected_evidences)
        out["page_localization_accuracy"] = page_localization_accuracy(
            predicted_evidences, expected_evidences
        )
    if e2e_predictions is not None and e2e_references is not None:
        out["end_to_end_task_success_rate"] = end_to_end_task_success_rate(
            e2e_predictions, e2e_references
        )
    return out
