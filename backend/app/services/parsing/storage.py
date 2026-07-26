"""Path-safe storage for sources, checkpoints, and generated artifacts."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol


class ObjectStore(Protocol):
    def write(self, relative_path: str, data: bytes) -> str: ...
    def read(self, relative_path: str) -> bytes: ...
    def delete_tree(self, relative_path: str) -> None: ...


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Storage path escapes configured root") from exc
        return candidate

    def write(self, relative_path: str, data: bytes) -> str:
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
        return relative_path

    def read(self, relative_path: str) -> bytes:
        return self.resolve(relative_path).read_bytes()

    def delete_tree(self, relative_path: str) -> None:
        target = self.resolve(relative_path)
        if target.exists():
            shutil.rmtree(target)

    def work_dir(self, relative_path: str) -> Path:
        target = self.resolve(relative_path)
        target.mkdir(parents=True, exist_ok=True)
        return target
