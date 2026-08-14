"""Persistent content-addressed cache for completed page results."""

from __future__ import annotations

import hashlib
import json

from app.services.parsing.storage import ObjectStore
from app.services.parsing.v2_pipeline import PageResult


def page_cache_key(page_png: bytes, *, mode: str, prompt_version: str) -> str:
    digest = hashlib.sha256()
    digest.update(b"paperplane-page-cache\0")
    digest.update(prompt_version.encode())
    digest.update(b"\0")
    digest.update(mode.encode())
    digest.update(b"\0")
    digest.update(page_png)
    return digest.hexdigest()


class PageResultCache:
    def __init__(self, store: ObjectStore) -> None:
        self.store = store

    @staticmethod
    def path(key: str) -> str:
        return f"cache/v2/pages/{key[:2]}/{key}.json"

    @staticmethod
    def evidence_path(key: str, evidence_id: str) -> str:
        digest = hashlib.sha256(evidence_id.encode()).hexdigest()
        return f"cache/v2/pages/{key[:2]}/{key}.evidence/{digest}.png"

    @staticmethod
    def evidence_index_path(key: str) -> str:
        return f"cache/v2/pages/{key[:2]}/{key}.evidence.json"

    def get(self, key: str) -> PageResult | None:
        try:
            result = PageResult.model_validate_json(self.store.read(self.path(key)))
        except (FileNotFoundError, KeyError, OSError, ValueError):
            return None
        evidence: dict[str, bytes] = {}
        try:
            index = json.loads(self.store.read(self.evidence_index_path(key)))
            evidence = {evidence_id: self.store.read(path) for evidence_id, path in index.items()}
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
            evidence = {}
        return result.model_copy(
            update={
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_input_tokens": 0,
                "cache_write_tokens": 0,
                "model_usage": {},
                "application_cache_hit": True,
                "evidence_artifacts": evidence,
            }
        )

    def put(self, key: str, result: PageResult) -> None:
        self.store.write(self.path(key), result.model_dump_json(indent=2).encode())
        index: dict[str, str] = {}
        for evidence_id, data in result.evidence_artifacts.items():
            path = self.evidence_path(key, evidence_id)
            self.store.write(path, data)
            index[evidence_id] = path
        self.store.write(self.evidence_index_path(key), json.dumps(index, indent=2).encode())
