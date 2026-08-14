"""Safe, temporary LibreOffice conversion for visual parsing."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from paperplane.ingest import OFFICE_EXTENSIONS, DocumentInputError

DEFAULT_CONVERSION_TIMEOUT_SECONDS = 180


def find_soffice() -> Path | None:
    """Locate LibreOffice without changing the process environment."""

    for command in ("soffice.com", "soffice.exe", "libreoffice"):
        located = shutil.which(command)
        if located:
            return Path(located)
    if os.name == "nt":
        candidates = (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "LibreOffice"
            / "program"
            / "soffice.com",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "LibreOffice"
            / "program"
            / "soffice.com",
        )
        return next((path for path in candidates if path.is_file()), None)
    return None


def convert_office_to_pdf(
    data: bytes,
    filename: str,
    *,
    max_bytes: int,
    timeout_seconds: int = DEFAULT_CONVERSION_TIMEOUT_SECONDS,
) -> bytes:
    """Convert one supported Office/OpenDocument file in an isolated profile."""

    suffix = Path(filename).suffix.casefold()
    if suffix not in OFFICE_EXTENSIONS:
        raise DocumentInputError("unsupported_type", "LibreOffice conversion requires Office input")
    executable = find_soffice()
    if executable is None:
        raise DocumentInputError(
            "libreoffice_missing",
            "LibreOffice is required for Office files. Run Paperplane.cmd to install it.",
        )

    safe_name = Path(filename).name or f"document{suffix}"
    with tempfile.TemporaryDirectory(prefix="paperplane-office-") as temporary:
        root = Path(temporary)
        source_dir = root / "source"
        output_dir = root / "output"
        profile_dir = root / "profile"
        source_dir.mkdir()
        output_dir.mkdir()
        profile_dir.mkdir()
        source = source_dir / safe_name
        source.write_bytes(data)
        command = [
            str(executable),
            f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(source),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DocumentInputError(
                "office_conversion_timeout", "LibreOffice conversion timed out"
            ) from exc
        output = output_dir / f"{source.stem}.pdf"
        if completed.returncode != 0 or not output.is_file():
            raise DocumentInputError(
                "office_conversion_failed", "LibreOffice could not convert this document"
            )
        converted = output.read_bytes()
        if not converted or len(converted) > max_bytes:
            raise DocumentInputError(
                "office_conversion_too_large", "Converted PDF exceeds the upload limit"
            )
        return converted


__all__ = ["convert_office_to_pdf", "find_soffice"]
