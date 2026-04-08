#!/usr/bin/env python3
"""End-to-end validation matrix against a running backend on localhost:8000.

Exercises every real scenario: PDF text, image OCR, Auto routing,
missing/invalid keys, invalid model selection.  Reports PASS / FAIL
for each test with the actual server response.

Usage:
    python scripts/e2e_validation.py
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000/api"


# ── helpers ──────────────────────────────────────────────────────────

def _make_pdf(text: str = "Invoice from Acme Corp.\nTotal: $1,234.56\nDate: 2025-03-15") -> bytes:
    """Create a minimal valid PDF with embedded text using PyMuPDF."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    buf = doc.tobytes()
    doc.close()
    return buf


def _make_png() -> bytes:
    """Create a tiny valid PNG image (1x1 white pixel)."""
    import struct, zlib
    sig = b"\x89PNG\r\n\x1a\n"
    def _chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = zlib.compress(b"\x00\xFF\xFF\xFF")
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", raw) + _chunk(b"IEND", b"")


async def upload(client: httpx.AsyncClient, name: str, data: bytes, mime: str = "application/pdf") -> str:
    """Upload a document and return its ID."""
    files = {"file": (name, io.BytesIO(data), mime)}
    r = await client.post(f"{BASE}/documents/", files=files)
    r.raise_for_status()
    return r.json()["id"]


async def create_schema(client: httpx.AsyncClient) -> str:
    """Create a test schema and return its ID."""
    body = {
        "name": f"e2e-invoice-{int(time.time())}",
        "fields": [
            {"name": "vendor", "field_type": "string", "required": True},
            {"name": "total", "field_type": "number", "required": True},
            {"name": "date", "field_type": "date", "required": False},
        ],
    }
    r = await client.post(f"{BASE}/schemas/", json=body)
    r.raise_for_status()
    return r.json()["id"]


async def submit_extraction(
    client: httpx.AsyncClient,
    doc_id: str,
    schema_id: str,
    *,
    ocr_provider: str = "auto",
    llm_provider: str = "auto",
    llm_model: str = "auto",
    expect_422: bool = False,
) -> dict:
    """Submit an extraction job and poll until terminal.

    If *expect_422* is True, return a synthetic dict with status=failed
    and the validation error in ``error`` without raising.
    """
    body = {
        "document_id": doc_id,
        "schema_id": schema_id,
        "ocr_provider": ocr_provider,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    }
    r = await client.post(f"{BASE}/extractions/", json=body)

    if expect_422:
        return {
            "id": "",
            "status": "rejected" if r.status_code == 422 else "unexpected",
            "error": r.text[:200],
            "http_status": r.status_code,
        }

    r.raise_for_status()
    ext_id = r.json()["id"]

    terminal = {"completed", "needs_review", "failed"}
    for _ in range(60):  # up to 60s
        await asyncio.sleep(1)
        r = await client.get(f"{BASE}/extractions/{ext_id}")
        r.raise_for_status()
        data = r.json()
        if data["status"] in terminal:
            return data
    return data  # return whatever we have after timeout


# ── test cases ───────────────────────────────────────────────────────

results: list[tuple[str, str, str]] = []  # (name, PASS|FAIL, detail)


def _err(ext: dict, maxlen: int = 120) -> str:
    """Safely extract error string from an extraction response."""
    return (ext.get("error") or "")[:maxlen]


def record(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append((name, status, detail))
    mark = "\u2705" if passed else "\u274C"
    print(f"  {mark} {name}: {status}" + (f"  \u2014 {detail}" if detail else ""))


async def run_matrix():
    print("=" * 70)
    print("E2E VALIDATION MATRIX")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=90) as client:

        # ── Preflight ────────────────────────────────────────────
        print("\n[Preflight] Health & config checks")
        try:
            r = await client.get(f"{BASE[:-4]}/health")
            record("Health endpoint", r.status_code == 200, f"status={r.status_code}")
        except Exception as exc:
            record("Health endpoint", False, str(exc))
            print("\n\u274C Server not reachable. Aborting.")
            return

        r = await client.get(f"{BASE}/providers/config")
        cfg = r.json()
        record("Config endpoint returns engines", "paddleocr" in cfg["parser_engines"], f"engines={cfg['parser_engines']}")
        record("Config PaddleOCR flag is off", cfg["ocr_engine_flags"]["paddleocr"] is False, f"flag={cfg['ocr_engine_flags']}")

        r = await client.get(f"{BASE}/providers/parsers")
        parsers = r.json()
        parser_ids = [p["id"] for p in parsers]
        pymupdf_entry = next((p for p in parsers if p["id"] == "pymupdf"), None)
        record(
            "Parsers endpoint excludes internal PyMuPDF",
            pymupdf_entry is None,
            f"ids={parser_ids}",
        )

        paddle_entry = next((p for p in parsers if p["id"] == "paddleocr"), None)
        record(
            "Parsers endpoint lists paddleocr",
            paddle_entry is not None,
            f"ids={parser_ids}",
        )
        if paddle_entry:
            record(
                "PaddleOCR reports enabled=false (flag off)",
                paddle_entry.get("enabled") is False,
                f"entry={paddle_entry}",
            )

        r = await client.get(f"{BASE}/providers/llm")
        llm_providers = r.json()
        llm_ids = [p["id"] for p in llm_providers]
        record("LLM providers listed", len(llm_ids) >= 3, f"ids={llm_ids}")

        # Check that at least one LLM reports missing key
        states = {p["id"]: p.get("availability", {}).get("state") for p in llm_providers}
        record(
            "All LLM providers report missing_api_key",
            all(s == "missing_api_key" for s in states.values()),
            f"states={states}",
        )

        # ── Create shared fixtures ───────────────────────────────
        print("\n[Fixtures] Upload docs & create schema")
        pdf_bytes = _make_pdf()
        png_bytes = _make_png()

        pdf_id = await upload(client, "invoice.pdf", pdf_bytes)
        record("Upload PDF", bool(pdf_id), f"doc_id={pdf_id}")

        png_id = await upload(client, "scan.png", png_bytes, "image/png")
        record("Upload PNG", bool(png_id), f"doc_id={png_id}")

        schema_id = await create_schema(client)
        record("Create schema", bool(schema_id), f"schema_id={schema_id}")

        # ── 1. PDF text with Auto parser (resolves to PyMuPDF) ────
        print("\n[1] PDF text extraction — Auto parser → PyMuPDF, explicit openai LLM")
        ext = await submit_extraction(
            client, pdf_id, schema_id,
            ocr_provider="auto", llm_provider="openai", llm_model="auto",
        )
        # Auto should pick pymupdf for PDF; then fail at LLM stage (no API key)
        record(
            "Auto resolves to pymupdf for PDF",
            ext.get("ocr_provider_used") == "pymupdf",
            f"status={ext['status']}, ocr_used={ext.get('ocr_provider_used')}, error={_err(ext)}",
        )
        record(
            "Fails at LLM stage (OCR succeeded)",
            ext["status"] == "failed" and "ocr" not in (ext.get("error") or "").lower(),
            f"error={_err(ext)}",
        )

        # ── 2. Image OCR — Auto routing, PaddleOCR disabled ─────
        print("\n[2] Image OCR — PaddleOCR disabled, Auto should fail gracefully")
        ext = await submit_extraction(
            client, png_id, schema_id,
            ocr_provider="auto", llm_provider="openai", llm_model="auto",
        )
        record(
            "Auto rejects PNG when no OCR engine enabled",
            ext["status"] == "failed",
            f"status={ext['status']}, error={_err(ext)}",
        )
        record(
            "Error explains no OCR for images",
            "will not fall back" in (ext.get("error") or "").lower() or "ocr" in (ext.get("error") or "").lower(),
            f"error={_err(ext)}",
        )

        # ── 3. Explicit PaddleOCR when feature flag is off ───────
        print("\n[3] Explicit PaddleOCR when feature flag is off")
        ext = await submit_extraction(
            client, png_id, schema_id,
            ocr_provider="paddleocr", llm_provider="openai", llm_model="auto",
        )
        record(
            "Disabled PaddleOCR request fails",
            ext["status"] == "failed",
            f"status={ext['status']}, error={_err(ext)}",
        )
        record(
            "Error mentions disabled/configuration",
            any(w in (ext.get("error") or "").lower() for w in ("disabled", "config", "enable")),
            f"error={_err(ext)}",
        )

        # ── 4. Explicit pymupdf is NOT in ParserEngine enum ─────
        print("\n[4] Non-enum parser value 'pymupdf' — should be rejected 422")
        ext = await submit_extraction(
            client, pdf_id, schema_id,
            ocr_provider="pymupdf", llm_provider="openai", llm_model="auto",
            expect_422=True,
        )
        record(
            "Non-enum parser value rejected by validation (422)",
            ext.get("http_status") == 422,
            f"http_status={ext.get('http_status')}, error={_err(ext)}",
        )

        # ── 5. Provider Auto with no API keys ────────────────────
        print("\n[5] LLM Provider Auto — all keys missing")
        ext = await submit_extraction(
            client, pdf_id, schema_id,
            ocr_provider="auto", llm_provider="auto", llm_model="auto",
        )
        record(
            "Auto LLM fails with clear error",
            ext["status"] == "failed",
            f"status={ext['status']}, error={_err(ext)}",
        )
        err_lower = (ext.get("error") or "").lower()
        record(
            "Error message mentions key/provider/configure",
            any(w in err_lower for w in ("key", "provider", "configured", "api", "credential")),
            f"error={_err(ext)}",
        )

        # ── 6. Explicit OpenAI with no OPENAI_API_KEY ────────────
        print("\n[6] Explicit OpenAI, no API key")
        ext = await submit_extraction(
            client, pdf_id, schema_id,
            ocr_provider="auto", llm_provider="openai", llm_model="auto",
        )
        record(
            "OpenAI without key fails",
            ext["status"] == "failed",
            f"status={ext['status']}, error={_err(ext)}",
        )
        record(
            "Error mentions API key",
            "key" in (ext.get("error") or "").lower() or "api" in (ext.get("error") or "").lower(),
            f"error={_err(ext)}",
        )

        # ── 7. Explicit Gemini with no GEMINI_API_KEY ────────────
        print("\n[7] Explicit Gemini, no API key")
        ext = await submit_extraction(
            client, pdf_id, schema_id,
            ocr_provider="auto", llm_provider="gemini", llm_model="auto",
        )
        record(
            "Gemini without key fails",
            ext["status"] == "failed",
            f"status={ext['status']}, error={_err(ext)}",
        )

        # ── 8. Explicit Anthropic with no key ────────────────────
        print("\n[8] Explicit Anthropic, no API key")
        ext = await submit_extraction(
            client, pdf_id, schema_id,
            ocr_provider="auto", llm_provider="anthropic", llm_model="auto",
        )
        record(
            "Anthropic without key fails",
            ext["status"] == "failed",
            f"status={ext['status']}, error={_err(ext)}",
        )

        # ── 9. Invalid model selection ───────────────────────────
        print("\n[9] Invalid model ID 'gpt-nonexistent-99'")
        ext = await submit_extraction(
            client, pdf_id, schema_id,
            ocr_provider="auto", llm_provider="openai", llm_model="gpt-nonexistent-99",
        )
        record(
            "Invalid model selection fails",
            ext["status"] == "failed",
            f"status={ext['status']}, error={_err(ext)}",
        )

        # ── 10. Completely invalid/unknown parser enum value ─────
        print("\n[10] Unknown parser engine ID sent as raw string")
        ext = await submit_extraction(
            client, pdf_id, schema_id,
            ocr_provider="glm_ocr_totally_fake", llm_provider="openai", llm_model="auto",
            expect_422=True,
        )
        record(
            "Unknown parser ID rejected (422)",
            ext.get("http_status") == 422,
            f"http_status={ext.get('http_status')}",
        )

        # ── 11. Unknown LLM provider value ───────────────────────
        print("\n[11] Unknown LLM provider ID")
        ext = await submit_extraction(
            client, pdf_id, schema_id,
            ocr_provider="auto", llm_provider="deepseek_fake", llm_model="auto",
            expect_422=True,
        )
        record(
            "Unknown LLM provider rejected (422)",
            ext.get("http_status") == 422,
            f"http_status={ext.get('http_status')}",
        )

        # ── 12. Retry endpoint ───────────────────────────────────
        print("\n[12] Retry a failed extraction")
        # Get last failed extraction
        r = await client.get(f"{BASE}/extractions/")
        all_exts = r.json()
        failed_ext = next((e for e in all_exts if e["status"] == "failed"), None)
        if failed_ext:
            ext_id = failed_ext["id"]
            r = await client.post(f"{BASE}/extractions/{ext_id}/retry")
            record(
                "Retry endpoint accepts failed job",
                r.status_code == 202,
                f"status_code={r.status_code}",
            )
            if r.status_code == 202:
                retried = r.json()
                record(
                    "Retried job resets to queued",
                    retried["status"] == "queued",
                    f"status={retried['status']}",
                )
                # Wait for it to reach terminal
                for _ in range(30):
                    await asyncio.sleep(1)
                    r2 = await client.get(f"{BASE}/extractions/{ext_id}")
                    final = r2.json()
                    if final["status"] in ("completed", "needs_review", "failed"):
                        break
                record(
                    "Retried job reaches terminal state",
                    final["status"] in ("completed", "needs_review", "failed"),
                    f"status={final['status']}",
                )

                # Now try retry immediately on the re-failed job
                # First retry it…
                if final["status"] == "failed":
                    r3 = await client.post(f"{BASE}/extractions/{ext_id}/retry")
                    # Then immediately attempt another retry (should 409)
                    r4 = await client.post(f"{BASE}/extractions/{ext_id}/retry")
                    record(
                        "Retry rejects non-failed job (409)",
                        r4.status_code == 409,
                        f"status_code={r4.status_code}, body={r4.text[:100]}",
                    )
        else:
            record("Retry endpoint (skip — no failed jobs)", False, "No failed extractions to test")

        # ── 13. History/list endpoint ────────────────────────────
        print("\n[13] List extractions")
        r = await client.get(f"{BASE}/extractions/")
        record(
            "List extractions returns array",
            r.status_code == 200 and isinstance(r.json(), list),
            f"count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )
        if r.status_code == 200:
            record(
                "Multiple extraction jobs recorded",
                len(r.json()) >= 5,
                f"count={len(r.json())}",
            )

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"  Total: {len(results)}  |  Passed: {passed}  |  Failed: {failed}")
    if failed:
        print("\n  FAILURES:")
        for name, status, detail in results:
            if status == "FAIL":
                print(f"    \u274C {name}: {detail}")
    print("=" * 70)
    return failed


if __name__ == "__main__":
    failures = asyncio.run(run_matrix())
    sys.exit(1 if failures else 0)
