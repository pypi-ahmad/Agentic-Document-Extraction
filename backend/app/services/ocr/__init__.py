"""OCR provider subsystem — registry, base types, and built-in engines."""

from app.services.ocr.base import (
    BaseOCRProvider,
    OCRBlock,
    OCRPageResult,
    OCRProviderError,
    OCRProviderUnavailableError,
    OCRResult,
    OCRTable,
)
from app.services.ocr.registry import (
    get_ocr_provider,
    list_ocr_provider_statuses,
    list_ocr_providers,
    register_provider,
)

__all__ = [
    "BaseOCRProvider",
    "OCRBlock",
    "OCRPageResult",
    "OCRProviderError",
    "OCRProviderUnavailableError",
    "OCRResult",
    "OCRTable",
    "get_ocr_provider",
    "list_ocr_provider_statuses",
    "list_ocr_providers",
    "register_provider",
]
