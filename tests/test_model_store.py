from pathlib import Path

from paperplane.model_store import MODEL_SET_VERSION, ModelStore


def _legacy_models(root: Path) -> tuple[Path, Path]:
    docling = root / "legacy-docling" / "models"
    required = {
        "docling-project--docling-layout-heron/model.safetensors": b"layout",
        "docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors": b"table",
        "docling-project--docling-models/model_artifacts/tableformer/accurate/tm_config.json": b"{}",
        "RapidOcr/PP-OCRv6_det_small.pth": b"det-torch",
        "RapidOcr/PP-OCRv6_rec_small.pth": b"rec-torch",
        "RapidOcr/ch_ptocr_mobile_v2.0_cls_mobile.pth": b"cls-torch",
        "RapidOcr/PP-OCRv6_det_small.onnx": b"det-onnx",
        "RapidOcr/PP-OCRv6_rec_small.onnx": b"rec-onnx",
        "RapidOcr/ch_ppocr_mobile_v2.0_cls_mobile.onnx": b"cls-onnx",
        "RapidOcr/ppocrv6_dict.txt": b"dictionary",
    }
    for relative, data in required.items():
        path = docling / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    layout = root / "legacy-layout"
    layout.mkdir()
    (layout / "config.json").write_text("{}", encoding="utf-8")
    (layout / "preprocessor_config.json").write_text("{}", encoding="utf-8")
    (layout / "model.safetensors").write_bytes(b"pp-layout")
    return docling, layout


def test_model_store_migrates_existing_weights_and_stays_offline(tmp_path: Path) -> None:
    legacy_docling, legacy_layout = _legacy_models(tmp_path)
    store = ModelStore(tmp_path / "permanent")

    assert store.migrate(legacy_docling, legacy_layout)
    assert store.finalize().ready

    for path in (legacy_docling.parent, legacy_layout):
        for file in path.rglob("*"):
            if file.is_file():
                file.unlink()

    status = store.check()
    assert status.ready
    assert status.model_set_version == MODEL_SET_VERSION
    assert status.file_count == 13


def test_model_store_detects_changed_file_size(tmp_path: Path) -> None:
    legacy_docling, legacy_layout = _legacy_models(tmp_path)
    store = ModelStore(tmp_path / "permanent")
    store.migrate(legacy_docling, legacy_layout)
    store.finalize()

    (store.layout_root / "model.safetensors").write_bytes(b"damaged")

    status = store.check()
    assert not status.ready
    assert "pp-doclayout-v3/model.safetensors" in status.invalid_files


def test_model_store_uses_versioned_runtime_paths(tmp_path: Path, monkeypatch) -> None:
    store = ModelStore(tmp_path / "models")

    store.configure_environment()

    assert store.root == tmp_path / "models" / "sets" / MODEL_SET_VERSION
    assert store.docling_cache == store.root / "docling"
    assert store.layout_root == store.root / "pp-doclayout-v3"
    assert __import__("os").environ["DOCLING_CACHE_DIR"] == str(store.docling_cache)
