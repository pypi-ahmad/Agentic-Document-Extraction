"""File upload handling utilities."""

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

SUPPORTED_FILE_TYPES = ("pdf", "png", "jpg", "jpeg", "tiff", "tif")
ALLOWED_EXTENSIONS = {f".{suffix}" for suffix in SUPPORTED_FILE_TYPES}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
}


class FileValidationError(Exception):
    pass


def validate_upload(file: UploadFile) -> None:
    """Validate an uploaded file before saving."""
    if not file.filename:
        raise FileValidationError("Filename is required.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise FileValidationError(f"Unsupported content type '{file.content_type}'.")


async def save_upload(file: UploadFile) -> tuple[str, str, int]:
    """Save an uploaded file to the uploads directory.

    Returns:
        (saved_filename, file_path_str, file_size)
    """
    validate_upload(file)

    ext = Path(file.filename or "file").suffix.lower()
    saved_name = f"{uuid.uuid4().hex}{ext}"
    dest = settings.upload_path / saved_name

    content = await file.read()
    file_size = len(content)

    if file_size > settings.max_upload_bytes:
        raise FileValidationError(
            f"File too large ({file_size // (1024 * 1024)}MB). "
            f"Maximum is {settings.max_upload_size_mb}MB."
        )

    dest.write_bytes(content)
    return saved_name, str(dest), file_size


def get_file_type(filename: str) -> str:
    """Return a normalized file type string."""
    ext = Path(filename).suffix.lower()
    type_map = {
        ".pdf": "pdf",
        ".png": "png",
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".tiff": "tiff",
        ".tif": "tiff",
    }
    return type_map.get(ext, "unknown")
