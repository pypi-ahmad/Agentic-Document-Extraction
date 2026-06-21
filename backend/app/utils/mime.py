"""Magic-byte MIME sniffing for uploaded files.

The frontend declares a content type, but a malicious or buggy client
can claim ``image/png`` while sending a Python script. We re-validate
the bytes against known file signatures before saving the upload.

This module is intentionally small. It does not depend on libmagic; it
recognises the four formats we support (PDF, PNG, JPEG, TIFF) and
raises on anything else. Anything we don't recognise is rejected, so
the parser layer never sees an unverified blob.
"""

from __future__ import annotations

from pathlib import Path

from app.constants import (
    ALLOWED_MAGIC_JPEG,
    ALLOWED_MAGIC_PDF,
    ALLOWED_MAGIC_PNG,
    ALLOWED_MAGIC_TIFF_BE,
    ALLOWED_MAGIC_TIFF_LE,
    UPLOAD_SNIFF_BYTES,
)
from app.utils.file_handler import FileValidationError

# (prefix, type-label) pairs. Order matters; the first match wins.
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (ALLOWED_MAGIC_PDF, "pdf"),
    (ALLOWED_MAGIC_PNG, "png"),
    (ALLOWED_MAGIC_JPEG, "jpeg"),
    (ALLOWED_MAGIC_TIFF_LE, "tiff"),
    (ALLOWED_MAGIC_TIFF_BE, "tiff"),
]


def sniff_mime(file_path: Path) -> str:
    """Return the verified file type from the file's magic bytes.

    Reads up to ``UPLOAD_SNIFF_BYTES`` from the start of the file. The
    extension is **not** trusted; the bytes are.

    Raises ``FileValidationError`` if the magic does not match any
    supported signature.
    """
    try:
        with file_path.open("rb") as fh:
            head = fh.read(UPLOAD_SNIFF_BYTES)
    except OSError as exc:
        raise FileValidationError(f"Could not read upload: {exc}") from exc

    if not head:
        raise FileValidationError("Uploaded file is empty.")

    for prefix, type_label in _MAGIC_SIGNATURES:
        if head.startswith(prefix):
            return type_label

    raise FileValidationError("Uploaded file does not match any supported magic signature.")


def mime_matches_extension(verified_type: str, declared_extension: str) -> bool:
    """Return True iff the verified type is consistent with the declared extension.

    Both are normalised to lowercase. The mapping is intentionally
    narrow: ``.tif`` and ``.tiff`` are both ``tiff``; ``.jpg`` and
    ``.jpeg`` are both ``jpeg``.
    """
    ext = declared_extension.lower().lstrip(".")
    alias = {"tif": "tiff", "jpg": "jpeg"}
    ext = alias.get(ext, ext)
    return ext == verified_type
