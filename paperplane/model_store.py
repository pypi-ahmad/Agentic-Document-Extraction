"""Permanent, versioned storage for Paperplane-owned model weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MODEL_SET_VERSION = "v1"
LAYOUT_MODEL_ID = "PaddlePaddle/PP-DocLayoutV3_safetensors"
LAYOUT_MODEL_REVISION = "97d101e6db2642e162a1d05392d1b0231c91033e"
DOCLING_DIRECTORIES = (
    "docling-project--docling-layout-heron",
    "docling-project--docling-models",
    "RapidOcr",
)
DOCLING_ANCHORS = (
    "docling-project--docling-layout-heron/model.safetensors",
    "docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors",
    "docling-project--docling-models/model_artifacts/tableformer/accurate/tm_config.json",
    "RapidOcr/PP-OCRv6_det_small.pth",
    "RapidOcr/PP-OCRv6_rec_small.pth",
    "RapidOcr/ch_ptocr_mobile_v2.0_cls_mobile.pth",
    "RapidOcr/PP-OCRv6_det_small.onnx",
    "RapidOcr/PP-OCRv6_rec_small.onnx",
    "RapidOcr/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    "RapidOcr/ppocrv6_dict.txt",
)
LAYOUT_ANCHORS = ("config.json", "preprocessor_config.json", "model.safetensors")


def default_model_root() -> Path:
    if sys.platform == "win32":
        local_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        local_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return local_data / "Paperplane" / "models"


@dataclass(frozen=True)
class ModelStoreStatus:
    ready: bool
    model_set_version: str
    file_count: int = 0
    invalid_files: tuple[str, ...] = ()


class ModelStore:
    def __init__(self, base_root: Path | None = None) -> None:
        self.base_root = Path(base_root) if base_root is not None else default_model_root()
        self.root = self.base_root / "sets" / MODEL_SET_VERSION
        self.docling_cache = self.root / "docling"
        self.docling_models = self.docling_cache / "models"
        self.layout_root = self.root / "pp-doclayout-v3"
        self.manifest = self.root / "manifest.json"

    def configure_environment(self) -> None:
        os.environ["DOCLING_CACHE_DIR"] = str(self.docling_cache)

    def anchors_ready(self) -> bool:
        return all((self.docling_models / path).is_file() for path in DOCLING_ANCHORS) and all(
            (self.layout_root / path).is_file() for path in LAYOUT_ANCHORS
        )

    def migrate(self, legacy_docling_models: Path, legacy_layout: Path | None) -> bool:
        for directory in DOCLING_DIRECTORIES:
            source = Path(legacy_docling_models) / directory
            if source.is_dir():
                shutil.copytree(source, self.docling_models / directory, dirs_exist_ok=True)
        if legacy_layout is not None and Path(legacy_layout).is_dir():
            shutil.copytree(legacy_layout, self.layout_root, dirs_exist_ok=True)
        return self.anchors_ready()

    def _managed_files(self) -> list[Path]:
        files: list[Path] = []
        for directory in DOCLING_DIRECTORIES:
            root = self.docling_models / directory
            if root.is_dir():
                files.extend(path for path in root.rglob("*") if path.is_file())
        if self.layout_root.is_dir():
            files.extend(path for path in self.layout_root.rglob("*") if path.is_file())
        return sorted(files)

    def finalize(self) -> ModelStoreStatus:
        if not self.anchors_ready():
            return ModelStoreStatus(
                ready=False,
                model_set_version=MODEL_SET_VERSION,
                invalid_files=self._missing_anchors(),
            )
        entries = []
        for path in self._managed_files():
            entries.append(
                {
                    "path": path.relative_to(self.root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        payload = {
            "schema": "paperplane.model-store.v1",
            "model_set_version": MODEL_SET_VERSION,
            "layout_model": {
                "repo_id": LAYOUT_MODEL_ID,
                "revision": LAYOUT_MODEL_REVISION,
            },
            "files": entries,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.manifest)
        return ModelStoreStatus(True, MODEL_SET_VERSION, len(entries))

    def check(self) -> ModelStoreStatus:
        try:
            payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ModelStoreStatus(False, MODEL_SET_VERSION, invalid_files=("manifest.json",))
        if payload.get("model_set_version") != MODEL_SET_VERSION:
            return ModelStoreStatus(False, MODEL_SET_VERSION, invalid_files=("manifest.json",))
        invalid: list[str] = []
        entries = payload.get("files")
        if not isinstance(entries, list):
            return ModelStoreStatus(False, MODEL_SET_VERSION, invalid_files=("manifest.json",))
        for entry in entries:
            if not isinstance(entry, dict):
                invalid.append("manifest.json")
                continue
            relative = str(entry.get("path", ""))
            path = self.root / relative
            if not path.is_file() or path.stat().st_size != entry.get("size"):
                invalid.append(relative)
        invalid.extend(path for path in self._missing_anchors() if path not in invalid)
        return ModelStoreStatus(not invalid, MODEL_SET_VERSION, len(entries), tuple(invalid))

    def _missing_anchors(self) -> tuple[str, ...]:
        missing = [
            f"docling/models/{path}"
            for path in DOCLING_ANCHORS
            if not (self.docling_models / path).is_file()
        ]
        missing.extend(
            f"pp-doclayout-v3/{path}"
            for path in LAYOUT_ANCHORS
            if not (self.layout_root / path).is_file()
        )
        return tuple(missing)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _legacy_docling_models() -> Path:
    configured = os.environ.get("DOCLING_CACHE_DIR")
    return Path(configured).expanduser() / "models" if configured else Path.home() / ".cache" / "docling" / "models"


def _legacy_layout_snapshot() -> Path | None:
    from huggingface_hub import snapshot_download

    try:
        return Path(
            snapshot_download(
                repo_id=LAYOUT_MODEL_ID,
                revision=LAYOUT_MODEL_REVISION,
                local_files_only=True,
            )
        )
    except Exception:
        return None


def _download_docling(store: ModelStore, *, force: bool = False) -> None:
    executable = Path(sys.executable).with_name(
        "docling-tools.exe" if sys.platform == "win32" else "docling-tools"
    )
    command = [
            str(executable),
            "models",
            "download",
            "layout",
            "tableformer",
            "rapidocr",
            "--output-dir",
            str(store.docling_models),
            "--quiet",
        ]
    if force:
        command.append("--force")
    subprocess.run(command, check=True)


def _download_layout(store: ModelStore, *, force: bool = False) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=LAYOUT_MODEL_ID,
        revision=LAYOUT_MODEL_REVISION,
        local_dir=store.layout_root,
        force_download=force,
    )


def prepare_model_store(*, download_missing: bool = True) -> ModelStoreStatus:
    store = ModelStore()
    legacy_docling = _legacy_docling_models()
    store.configure_environment()
    status = store.check()
    if status.ready:
        return status
    legacy_layout = _legacy_layout_snapshot()
    print(f"Verifying permanent model set {MODEL_SET_VERSION}...")
    had_manifest = store.manifest.is_file()
    migrated_ready = store.migrate(legacy_docling, legacy_layout)
    if had_manifest:
        status = store.check()
        if status.ready:
            print("Migrated existing model weights without downloading.")
            return status
    elif migrated_ready:
        print("Migrated existing model weights without downloading.")
        return store.finalize()
    if not download_missing:
        return store.check()
    if migrated_ready and status.invalid_files == ("manifest.json",):
        return store.finalize()
    invalid_docling = any(path.startswith("docling/") for path in status.invalid_files)
    invalid_layout = any(path.startswith("pp-doclayout-v3/") for path in status.invalid_files)
    if invalid_docling or not all(
        (store.docling_models / path).is_file() for path in DOCLING_ANCHORS
    ):
        print("Downloading missing Docling and RapidOCR weights...")
        _download_docling(store, force=invalid_docling)
    if invalid_layout or not all((store.layout_root / path).is_file() for path in LAYOUT_ANCHORS):
        print("Downloading missing PP-DocLayoutV3 weights...")
        _download_layout(store, force=invalid_layout)
    return store.finalize()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", required=True)
    args = parser.parse_args()
    if not args.prepare:
        return 2
    status = prepare_model_store()
    if not status.ready:
        print("Permanent model store is incomplete.", file=sys.stderr)
        return 1
    print(f"Permanent model set {status.model_set_version} is ready ({status.file_count} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
