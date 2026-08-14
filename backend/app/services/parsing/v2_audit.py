"""Private replay manifests and tamper-evident evidence bundles."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

from app.services.parsing.storage import ObjectStore

AUDIT_SCHEMA_VERSION = "paperplane-audit/v1"


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_path(job_id: str, data: bytes, suffix: str = "bin") -> str:
    return f"jobs-v2/{job_id}/audit/blobs/{sha256(data)}.{suffix}"


def write_blob(store: ObjectStore, job_id: str, data: bytes, suffix: str = "bin") -> dict[str, Any]:
    path = blob_path(job_id, data, suffix)
    store.write(path, data)
    return {"sha256": sha256(data), "size": len(data), "path": path}


def page_manifest_path(job_id: str, page_number: int) -> str:
    return f"jobs-v2/{job_id}/audit/pages/p{page_number:04d}.json"


def write_page_manifest(
    store: ObjectStore,
    *,
    job_id: str,
    page_number: int,
    recipe: dict[str, Any],
    source_sha256: str,
    page_image: bytes,
    calls: list[dict[str, Any]],
    result: dict[str, Any] | None,
    evidence: dict[str, bytes],
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    image_ref = write_blob(store, job_id, page_image, "png")
    evidence_refs = {
        evidence_id: write_blob(store, job_id, data, "png")
        for evidence_id, data in evidence.items()
    }
    manifest: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "job_id": job_id,
        "page_number": page_number,
        "source_sha256": source_sha256,
        "recipe": recipe,
        "page_image": image_ref,
        "calls": calls,
        "evidence": evidence_refs,
        "result": result,
        "failure": failure,
    }
    manifest["integrity_sha256"] = sha256(canonical_json(manifest))
    store.write(page_manifest_path(job_id, page_number), json.dumps(manifest, indent=2).encode())
    return manifest


def build_bundle(
    store: ObjectStore,
    *,
    job_id: str,
    source_path: str,
    source_sha256: str,
    recipe: dict[str, Any],
    page_count: int,
    extra_files: dict[str, bytes] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page_number in range(1, page_count + 1):
        try:
            pages.append(json.loads(store.read(page_manifest_path(job_id, page_number))))
        except (FileNotFoundError, OSError, ValueError):
            pages.append({"page_number": page_number, "missing_manifest": True})
    manifest: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "job_id": job_id,
        "source_sha256": source_sha256,
        "recipe": recipe,
        "pages": pages,
    }
    manifest["integrity_sha256"] = sha256(canonical_json(manifest))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("source/document", store.read(source_path))
        written: set[str] = set()
        for page in pages:
            page_number = int(page["page_number"])
            archive.writestr(f"pages/p{page_number:04d}.json", json.dumps(page, indent=2))
            refs = [page.get("page_image"), *page.get("evidence", {}).values()]
            for ref in refs:
                if isinstance(ref, dict) and ref.get("path") and ref["sha256"] not in written:
                    archive.writestr(f"blobs/{ref['sha256']}", store.read(str(ref["path"])))
                    written.add(str(ref["sha256"]))
        for name, data in (extra_files or {}).items():
            archive.writestr(name, data)
    return output.getvalue(), manifest


def verify_manifest(manifest: dict[str, Any]) -> bool:
    expected = manifest.get("integrity_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "integrity_sha256"}
    return isinstance(expected, str) and expected == sha256(canonical_json(unsigned))


__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "build_bundle",
    "canonical_json",
    "page_manifest_path",
    "sha256",
    "verify_manifest",
    "write_blob",
    "write_page_manifest",
]
