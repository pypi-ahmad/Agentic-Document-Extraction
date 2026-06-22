"""Schema-aware field strategies for v0.5.0.

A "field strategy" is a typed validator + post-processor for one
of the field kinds v0.5.0 understands:

* ``string`` — generic text (default)
* ``number`` — numeric
* ``boolean`` — true/false
* ``date`` — ISO 8601
* ``list`` — list of items
* ``object`` — nested object
* ``currency`` — currency amount + ISO 4217 code
* ``id`` — identifier (with check-digit validation hooks)
* ``address`` — postal address
* ``table`` — table of rows
* ``signature`` — signature block (binary presence + bbox)

Each strategy knows:

* How to **normalize** the LLM's raw value into the canonical
  representation.
* How to **validate** the canonical value (e.g. ISO 8601 date).
* A list of **regex hints** that can be pre-compiled once and
  reused for fast first-pass matching against the document text.
* A **prompt fragment** the LLM extractor can include in v2/extraction.md
  to nudge it toward the right output format.

Public API
----------

* :class:`FieldStrategy` — base class.
* :func:`get_strategy` — factory by kind.
* :class:`FieldValidationError` — typed error.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ── Errors ──────────────────────────────────────────────────────────


class FieldValidationError(ValueError):
    """Raised when a value fails its strategy's validation."""


# ── Base strategy ──────────────────────────────────────────────────


@dataclass
class FieldStrategy(ABC):
    """Base class for schema-aware field strategies."""

    kind: str = "string"
    """Stable string identifier for the field kind."""

    @abstractmethod
    def normalize(self, value: Any) -> Any:
        """Normalize a raw LLM value to the canonical representation."""

    @abstractmethod
    def validate(self, value: Any) -> list[str]:
        """Return a list of validation error messages. Empty = valid."""

    @property
    @abstractmethod
    def prompt_fragment(self) -> str:
        """A short prompt fragment hinting at the expected output format."""

    @property
    def regex_hints(self) -> list[re.Pattern[str]]:
        """Optional list of regex patterns that the value often matches."""

        return []


# ── String strategy (default) ─────────────────────────────────────


class StringStrategy(FieldStrategy):
    kind = "string"

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        return str(value).strip()

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if not isinstance(value, str):
            return [f"expected string, got {type(value).__name__}"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return "Return a short single-line string."


# ── Number strategy ───────────────────────────────────────────────


class NumberStrategy(FieldStrategy):
    kind = "number"

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            # bool is a subclass of int — disallow silently
            raise FieldValidationError("expected number, got bool")
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            cleaned = value.replace(",", "").replace("$", "").strip()
            try:
                if "." in cleaned:
                    return float(cleaned)
                return int(cleaned)
            except ValueError as exc:
                raise FieldValidationError(f"cannot parse number: {value!r}") from exc
        raise FieldValidationError(f"cannot coerce to number: {value!r}")

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return [f"expected number, got {type(value).__name__}"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return "Return a numeric value (not a string). No thousand separators, no currency symbols."

    @property
    def regex_hints(self) -> list[re.Pattern[str]]:
        return [
            re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"),
            re.compile(r"\b\d+\.\d+\b"),
            re.compile(r"\b\d+\b"),
        ]


# ── Boolean strategy ──────────────────────────────────────────────


class BooleanStrategy(FieldStrategy):
    kind = "boolean"

    _TRUE_TOKENS = frozenset({"true", "yes", "y", "1", "t"})
    _FALSE_TOKENS = frozenset({"false", "no", "n", "0", "f"})

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in self._TRUE_TOKENS:
                return True
            if lowered in self._FALSE_TOKENS:
                return False
        raise FieldValidationError(f"cannot coerce to bool: {value!r}")

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if not isinstance(value, bool):
            return [f"expected bool, got {type(value).__name__}"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return "Return true or false (JSON booleans)."


# ── Date strategy (ISO 8601) ──────────────────────────────────────


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
)


class DateStrategy(FieldStrategy):
    kind = "date"

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            # Try common formats
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%d %B %Y", "%Y/%m/%d"):
                try:
                    from datetime import datetime

                    return datetime.strptime(text, fmt).date().isoformat()
                except ValueError:
                    continue
            if _ISO_DATE_RE.match(text):
                return text
            if _ISO_DATETIME_RE.match(text):
                return text.split("T")[0].split(" ")[0]
            raise FieldValidationError(f"unrecognized date format: {text!r}")
        raise FieldValidationError(f"expected date string, got {type(value).__name__}")

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if not isinstance(value, str):
            return [f"expected date string, got {type(value).__name__}"]
        if not _ISO_DATE_RE.match(value):
            return [f"expected ISO 8601 date (YYYY-MM-DD), got {value!r}"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return "Return the date in ISO 8601 format: YYYY-MM-DD."

    @property
    def regex_hints(self) -> list[re.Pattern[str]]:
        return [
            re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
            re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
        ]


# ── Currency strategy ─────────────────────────────────────────────


class CurrencyStrategy(FieldStrategy):
    kind = "currency"

    ISO_4217 = re.compile(r"^[A-Z]{3}$")

    def normalize(self, value: Any) -> Any:
        """Return ``{"amount": float, "currency": "USD"}`` or raise."""

        if value is None:
            return None
        if isinstance(value, dict):
            amount = value.get("amount")
            currency = (value.get("currency") or "USD").upper()
            if not self.ISO_4217.match(currency):
                raise FieldValidationError(f"invalid currency code: {currency}")
            return {"amount": float(amount), "currency": currency}
        if isinstance(value, (int, float)):
            return {"amount": float(value), "currency": "USD"}
        if isinstance(value, str):
            text = value.strip()
            # Parse "1,234.56 USD" or "USD 1,234.56"
            m = re.match(r"^\s*([A-Z]{3})?\s*([\d,]+(?:\.\d+)?)\s*([A-Z]{3})?\s*$", text)
            if m:
                c1, amount, c2 = m.groups()
                currency = (c1 or c2 or "USD").upper()
                return {"amount": float(amount.replace(",", "")), "currency": currency}
            raise FieldValidationError(f"unrecognized currency format: {text!r}")
        raise FieldValidationError(f"cannot coerce to currency: {value!r}")

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if not isinstance(value, dict):
            return [f"expected currency dict, got {type(value).__name__}"]
        if "amount" not in value:
            return ["missing 'amount' key"]
        if not isinstance(value["amount"], (int, float)):
            return ["'amount' must be numeric"]
        currency = value.get("currency", "")
        if not self.ISO_4217.match(currency):
            return [f"invalid currency code: {currency!r}"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return 'Return the amount as a JSON object: {"amount": <number>, "currency": "<ISO 4217 code>"}.'


# ── ID strategy ───────────────────────────────────────────────────


@dataclass
class IDStrategy(FieldStrategy):
    """Generic identifier strategy. Subclass for check-digit validation."""

    kind: str = "id"
    min_length: int = 1
    max_length: int = 64
    pattern: re.Pattern[str] | None = None

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        text = value.strip().upper()
        if len(text) < self.min_length:
            raise FieldValidationError(f"id too short: {len(text)} < {self.min_length}")
        if len(text) > self.max_length:
            raise FieldValidationError(f"id too long: {len(text)} > {self.max_length}")
        if self.pattern and not self.pattern.match(text):
            raise FieldValidationError(f"id does not match expected pattern: {text!r}")
        return text

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if not isinstance(value, str):
            return [f"expected id string, got {type(value).__name__}"]
        if len(value) < self.min_length:
            return [f"id too short: {len(value)} < {self.min_length}"]
        if len(value) > self.max_length:
            return [f"id too long: {len(value)} > {self.max_length}"]
        if self.pattern and not self.pattern.match(value):
            return ["id does not match expected pattern"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return "Return the identifier as a single string, preserving the original formatting."


# ── Address strategy ──────────────────────────────────────────────


class AddressStrategy(FieldStrategy):
    kind = "address"

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return {"raw": " ".join(value.split())}
        if isinstance(value, dict):
            return {
                k: (v if not isinstance(v, str) else " ".join(v.split())) for k, v in value.items()
            }
        raise FieldValidationError(f"expected address string or dict, got {type(value).__name__}")

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if isinstance(value, str):
            if len(value.strip()) < 5:
                return ["address looks too short"]
            return []
        if isinstance(value, dict):
            if not value:
                return ["address dict is empty"]
            return []
        return [f"expected address string or dict, got {type(value).__name__}"]

    @property
    def prompt_fragment(self) -> str:
        return "Return the address as a single string. If possible, return a JSON object with keys: street, city, state, postal_code, country."

    @property
    def regex_hints(self) -> list[re.Pattern[str]]:
        return [
            re.compile(r"\b\d{1,5}\s+[A-Z][a-z]+\s+(?:St|Ave|Rd|Blvd|Lane|Ln|Drive|Dr)\b"),
            re.compile(r"\b\d{5}(?:-\d{4})?\b"),  # US zip
        ]


# ── Table strategy ────────────────────────────────────────────────


class TableStrategy(FieldStrategy):
    kind = "table"

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, list):
            raise FieldValidationError(f"expected list of rows, got {type(value).__name__}")
        rows: list[list[str]] = []
        for row in value:
            if isinstance(row, list):
                rows.append([str(cell) for cell in row])
            elif isinstance(row, dict):
                # Convert dict row to list (preserve order)
                rows.append([str(v) for v in row.values()])
            else:
                raise FieldValidationError("each row must be a list or dict")
        return rows

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if not isinstance(value, list):
            return [f"expected list of rows, got {type(value).__name__}"]
        if not value:
            return ["table is empty"]
        # All rows must be lists of the same length
        widths = {len(r) if isinstance(r, list) else -1 for r in value}
        if -1 in widths:
            return ["each row must be a list"]
        if len(widths) > 1:
            return [f"rows have inconsistent widths: {sorted(widths)}"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return 'Return the table as a JSON array of arrays: [["cell1", "cell2"], ["cell3", "cell4"]]. The first row should be the header.'


# ── Signature strategy ───────────────────────────────────────────


class SignatureStrategy(FieldStrategy):
    """Signature block: present/absent + optional bbox."""

    kind = "signature"

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return {"present": value, "bbox": None}
        if isinstance(value, dict):
            present = bool(value.get("present", value.get("signed", False)))
            bbox = value.get("bbox")
            if isinstance(bbox, list) and len(bbox) == 4:
                bbox = tuple(float(x) for x in bbox)
            else:
                bbox = None
            return {"present": present, "bbox": bbox}
        if isinstance(value, str):
            return {
                "present": value.strip().lower() in {"yes", "true", "1", "signed"},
                "bbox": None,
            }
        raise FieldValidationError(f"cannot coerce to signature: {value!r}")

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if not isinstance(value, dict):
            return [f"expected signature dict, got {type(value).__name__}"]
        if "present" not in value:
            return ["missing 'present' key"]
        if not isinstance(value["present"], bool):
            return ["'present' must be bool"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return (
            'Return {"present": true|false, "bbox": [x0, y0, x1, y1] (omit bbox if no signature).'
        )


# ── List strategy ─────────────────────────────────────────────────


class ListStrategy(FieldStrategy):
    kind = "list"

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, list):
            raise FieldValidationError(f"expected list, got {type(value).__name__}")
        return [str(x) for x in value]

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if not isinstance(value, list):
            return [f"expected list, got {type(value).__name__}"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return "Return a JSON array of strings."


# ── Object strategy ───────────────────────────────────────────────


class ObjectStrategy(FieldStrategy):
    kind = "object"

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise FieldValidationError(f"expected object, got {type(value).__name__}")
        return value

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return ["required"]
        if not isinstance(value, dict):
            return [f"expected object, got {type(value).__name__}"]
        return []

    @property
    def prompt_fragment(self) -> str:
        return "Return a JSON object."


# ── Factory ────────────────────────────────────────────────────────


_STRATEGIES: dict[str, FieldStrategy] = {
    "string": StringStrategy(),
    "number": NumberStrategy(),
    "boolean": BooleanStrategy(),
    "date": DateStrategy(),
    "currency": CurrencyStrategy(),
    "id": IDStrategy(),
    "address": AddressStrategy(),
    "table": TableStrategy(),
    "signature": SignatureStrategy(),
    "list": ListStrategy(),
    "object": ObjectStrategy(),
}


def get_strategy(kind: str) -> FieldStrategy:
    """Return the strategy for a field kind, or the string strategy as fallback."""

    return _STRATEGIES.get(kind, _STRATEGIES["string"])


def available_kinds() -> list[str]:
    """Return the list of supported field kinds."""

    return sorted(_STRATEGIES.keys())


def normalize_with_strategy(value: Any, kind: str) -> tuple[Any, list[str]]:
    """Normalize + validate ``value`` under ``kind``. Returns (value, errors)."""

    strategy = get_strategy(kind)
    try:
        normalized = strategy.normalize(value)
    except FieldValidationError as exc:
        return value, [str(exc)]
    errors = strategy.validate(normalized)
    return normalized, errors


# ── Helper: build a fields_block for the v2 prompt ───────────────


def render_fields_block(fields: list[dict[str, Any]]) -> str:
    """Render a fields_block for v2/extraction.md given a list of field defs.

    Each field def is a dict with ``name``, optional ``kind``, and
    optional ``description``. The output includes the strategy's
    prompt fragment so the LLM knows the expected format.
    """

    lines: list[str] = []
    for f in fields:
        name = f.get("name") or "?"
        kind = f.get("kind") or f.get("field_type") or "string"
        description = f.get("description") or ""
        strategy = get_strategy(kind)
        hint = strategy.prompt_fragment
        line = f"- {name}"
        if description:
            line += f" — {description}"
        line += f" [{kind}]: {hint}"
        lines.append(line)
    return "\n".join(lines)
