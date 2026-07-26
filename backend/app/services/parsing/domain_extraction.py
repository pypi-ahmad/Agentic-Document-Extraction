"""Evidence-grounded document classification and profile extraction."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.parsing.contracts import BoundingBox, ContextChunk

DocumentProfile = Literal[
    "technical_document",
    "scientific_paper",
    "invoice",
    "insurance_claim",
    "healthcare_form",
    "general_scanned",
]


class EvidenceReference(BaseModel):
    page: int = Field(ge=1)
    source_page: int | None = Field(default=None, ge=1)
    region_id: str
    bbox: BoundingBox
    cell_id: str | None = None
    source_bbox: dict[str, Any] | None = None


class GroundedValue(BaseModel):
    value: Any = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    method: Literal["rule", "model", "rule_only_fallback"] = "rule"
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class DomainExtraction(BaseModel):
    schema_version: Literal["paperplane-domain-extraction/v2"] = "paperplane-domain-extraction/v2"
    requested_profile: str
    detected_profile: DocumentProfile
    classification_confidence: float = Field(ge=0, le=1)
    complete: bool
    processed_pages: list[int]
    missing_pages: list[int]
    fields: dict[str, GroundedValue]
    warnings: list[str] = Field(default_factory=list)


_CUES: dict[DocumentProfile, tuple[str, ...]] = {
    "technical_document": (
        "installation",
        "configuration",
        "prerequisite",
        "procedure",
        "warning",
        "revision",
    ),
    "scientific_paper": (
        "abstract",
        "methodology",
        "methods",
        "results",
        "conclusion",
        "doi",
        "references",
    ),
    "invoice": (
        "invoice number",
        "invoice #",
        "subtotal",
        "grand total",
        "amount due",
        "payment terms",
        "unit price",
    ),
    "insurance_claim": (
        "claim number",
        "policy number",
        "date of loss",
        "claimant",
        "insured",
        "claimed amount",
    ),
    "healthcare_form": (
        "patient name",
        "medical record",
        "date of birth",
        "diagnosis",
        "medication",
        "provider",
    ),
    "general_scanned": (),
}

_FIELDS: dict[DocumentProfile, dict[str, tuple[str, ...]]] = {
    "technical_document": {
        "title": ("title",),
        "document_id": ("document id", "document number"),
        "version": ("version", "revision"),
        "revision_date": ("revision date", "effective date"),
        "authors": ("author", "prepared by"),
        "product_or_system": ("product", "system"),
        "purpose": ("purpose", "overview"),
        "prerequisites": ("prerequisite",),
        "procedures": ("procedure", "steps"),
        "warnings": ("warning", "caution"),
        "references": ("references",),
    },
    "scientific_paper": {
        "title": ("title",),
        "authors": ("author",),
        "affiliations": ("affiliation", "university", "institute"),
        "abstract": ("abstract",),
        "keywords": ("keywords",),
        "doi": ("doi",),
        "journal": ("journal",),
        "publication_date": ("published", "publication date"),
        "methods": ("methods", "methodology"),
        "datasets": ("dataset", "data source"),
        "results": ("results",),
        "conclusions": ("conclusion", "conclusions"),
        "references": ("references",),
    },
    "invoice": {
        "invoice_number": ("invoice number", "invoice #", "invoice no"),
        "issue_date": ("invoice date", "issue date"),
        "due_date": ("due date",),
        "purchase_order": ("purchase order", "po number", "po #"),
        "vendor": ("vendor", "seller", "from"),
        "customer": ("customer", "bill to", "buyer"),
        "currency": ("currency",),
        "subtotal": ("subtotal",),
        "tax": ("tax", "vat"),
        "total": ("amount due", "grand total", "total"),
        "payment_terms": ("payment terms", "terms"),
        "line_items": ("description", "quantity", "unit price", "amount"),
    },
    "insurance_claim": {
        "claim_number": ("claim number", "claim #"),
        "policy_number": ("policy number", "policy #"),
        "claimant": ("claimant",),
        "insured": ("insured",),
        "claim_type": ("claim type", "type of loss"),
        "loss_date": ("date of loss", "loss date"),
        "reported_date": ("reported date", "date reported"),
        "incident_summary": ("incident", "description of loss"),
        "service_providers": ("service provider", "provider"),
        "claimed_amount": ("claimed amount", "amount claimed"),
        "approved_amount": ("approved amount", "amount approved"),
        "status": ("claim status", "status"),
        "claim_items": ("item", "amount", "service"),
    },
    "healthcare_form": {
        "form_type": ("form type", "form"),
        "patient_name": ("patient name", "patient"),
        "medical_record_number": ("medical record", "mrn"),
        "date_of_birth": ("date of birth", "dob"),
        "encounter_date": ("encounter date", "visit date", "service date"),
        "providers": ("provider", "physician", "clinician"),
        "diagnoses": ("diagnosis", "diagnoses", "icd"),
        "procedures": ("procedure", "cpt"),
        "medications": ("medication", "prescription"),
        "allergies": ("allergies", "allergy"),
        "vitals": ("vitals", "blood pressure", "temperature"),
        "payer": ("payer", "insurance"),
        "member_id": ("member id", "subscriber id"),
        "signatures": ("signature", "signed by"),
    },
    "general_scanned": {
        "title": ("title",),
        "document_type": ("document type", "type"),
        "dates": ("date",),
        "people": ("name", "person"),
        "organizations": ("organization", "company"),
        "identifiers": ("number", "id"),
        "summary": (),
        "key_facts": (),
        "tables": ("table",),
    },
}


def classify_profile(chunks: list[ContextChunk]) -> tuple[DocumentProfile, float]:
    text = "\n".join(chunk.text for chunk in chunks[:80]).casefold()
    scores = {
        profile: sum(1 for cue in cues if cue in text)
        for profile, cues in _CUES.items()
        if profile != "general_scanned"
    }
    profile, score = max(scores.items(), key=lambda item: item[1], default=("general_scanned", 0))
    if score < 2:
        return "general_scanned", 0.5
    runner_up = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
    confidence = min(0.98, 0.65 + (score - runner_up) * 0.08)
    return profile, confidence


def extract_domain(
    chunks: list[ContextChunk],
    requested_profile: str,
    *,
    expected_pages: list[int],
) -> DomainExtraction:
    detected, confidence = classify_profile(chunks)
    profile: DocumentProfile = (
        detected if requested_profile == "auto" else requested_profile  # type: ignore[assignment]
    )
    processed_pages = sorted({chunk.page for chunk in chunks})
    missing_pages = sorted(set(expected_pages) - set(processed_pages))
    fields = {
        name: _find_value(chunks, labels, fallback=name in {"summary", "key_facts"})
        for name, labels in _FIELDS[profile].items()
    }
    warnings = ["partial_document"] if missing_pages else []
    return DomainExtraction(
        requested_profile=requested_profile,
        detected_profile=profile,
        classification_confidence=confidence if requested_profile == "auto" else 1.0,
        complete=not missing_pages,
        processed_pages=processed_pages,
        missing_pages=missing_pages,
        fields=fields,
        warnings=warnings,
    )


def _find_value(
    chunks: list[ContextChunk], labels: tuple[str, ...], *, fallback: bool = False
) -> GroundedValue:
    for chunk in chunks:
        normalized = " ".join(chunk.text.split())
        folded = normalized.casefold()
        if labels and not any(label in folded for label in labels):
            continue
        value = _after_label(normalized, labels) if labels else normalized
        if not value:
            continue
        return GroundedValue(
            value=value[:4000],
            confidence=0.82 if labels else 0.6,
            evidence=[
                EvidenceReference(
                    page=chunk.page,
                    source_page=chunk.source_page or chunk.page,
                    region_id=chunk.id,
                    bbox=chunk.bbox,
                    source_bbox=chunk.source_bbox,
                )
            ],
            candidates=[{"value": value[:4000], "method": "label_match", "region_id": chunk.id}],
        )
    if fallback:
        for chunk in chunks:
            if chunk.text.strip():
                return GroundedValue(
                    value=chunk.text.strip()[:4000],
                    confidence=0.5,
                    evidence=[
                        EvidenceReference(
                            page=chunk.page,
                            source_page=chunk.source_page or chunk.page,
                            region_id=chunk.id,
                            bbox=chunk.bbox,
                            source_bbox=chunk.source_bbox,
                        )
                    ],
                    candidates=[
                        {
                            "value": chunk.text.strip()[:4000],
                            "method": "fallback",
                            "region_id": chunk.id,
                        }
                    ],
                )
    return GroundedValue(value=None, confidence=0, evidence=[])


def _after_label(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*(?:[:#-]|\bis\b)?\s*(.+)", text, re.I)
        if match:
            return match.group(1).strip()
    return text.strip()
