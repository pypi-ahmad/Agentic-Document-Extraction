"""Paperplane's framework-neutral grounded document parser."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    """Keep lightweight contracts and benchmark tools free from OCR import cost."""

    if name in {"ParseResponse", "ProcessingStrategy"}:
        from paperplane import contracts

        return getattr(contracts, name)
    if name in {"MODEL_MODES", "AgenticDocumentParser"}:
        from paperplane import parser

        return getattr(parser, name)
    if name in {"parse_document", "parse_documents"}:
        from paperplane import runtime

        return getattr(runtime, name)
    raise AttributeError(name)


__all__ = [
    "MODEL_MODES",
    "AgenticDocumentParser",
    "ParseResponse",
    "ProcessingStrategy",
    "parse_document",
    "parse_documents",
]
