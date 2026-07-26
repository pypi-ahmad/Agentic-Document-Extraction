from app.services.parsing.v2_cache import PageResultCache, page_cache_key
from app.services.parsing.v2_pipeline import PageResult


class _Store:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def write(self, path: str, data: bytes) -> str:
        self.values[path] = data
        return path

    def read(self, path: str) -> bytes:
        return self.values[path]


def test_page_cache_key_changes_with_mode_prompt_or_pixels() -> None:
    base = page_cache_key(b"page-a", mode="balanced", prompt_version="v2")

    assert base != page_cache_key(b"page-b", mode="balanced", prompt_version="v2")
    assert base != page_cache_key(b"page-a", mode="audit", prompt_version="v2")
    assert base != page_cache_key(b"page-a", mode="balanced", prompt_version="v3")


def test_cache_hit_does_not_rebill_stored_openai_usage() -> None:
    store = _Store()
    cache = PageResultCache(store)
    result = PageResult(
        page_number=1,
        chunks=[],
        markdown="",
        input_tokens=100,
        output_tokens=10,
        cached_input_tokens=50,
    )
    key = page_cache_key(b"page", mode="balanced", prompt_version="v2")
    cache.put(key, result)

    hit = cache.get(key)

    assert hit is not None and hit.application_cache_hit is True
    assert hit.input_tokens == 0
    assert hit.output_tokens == 0
    assert hit.cached_input_tokens == 0
