"""Run the live Audit extractor and score its Markdown against reference outputs."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

import httpx

from app.config import settings
from app.services.parsing.ingest import inspect_document, render_page
from app.services.parsing.openai_document import OpenAIDocumentAdapter
from app.services.parsing.v2_accuracy import classify_markdown_types, compare_markdown_accuracy
from app.services.parsing.v2_contracts import ProcessingMode, mode_policy
from app.services.parsing.v2_pipeline import V2PageProcessor

PAGE_BREAK = "\n\n<!-- PAGE BREAK -->\n\n"
ACCURACY_GATE = 0.95


async def run(args: argparse.Namespace) -> dict:
    source = args.source.read_bytes()
    expected = args.ground_truth.read_text(encoding="utf-8")
    peer = args.peer.read_text(encoding="utf-8") if args.peer else None
    inspected = inspect_document(
        source,
        args.source.name,
        max_bytes=settings.max_upload_bytes,
        max_pages=settings.max_document_pages,
    )
    mode = ProcessingMode.AUDIT
    source_sha256 = hashlib.sha256(source).hexdigest()
    pages = []
    usage = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    timeout = httpx.Timeout(settings.openai_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as http:
        processor = V2PageProcessor(
            OpenAIDocumentAdapter(
                http,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        )
        async def process(page_number: int):
            rendered = render_page(
                source,
                args.source.name,
                page_number,
                mode_policy(mode).base_dpi,
            )
            result = await processor.process_page(
                source=source,
                filename=args.source.name,
                source_sha256=source_sha256,
                page=rendered,
                mode=mode,
            )
            print(f"completed page {page_number}", file=sys.stderr, flush=True)
            return result

        semaphore = asyncio.Semaphore(settings.v2_worker_count)

        async def limited(page_number: int):
            async with semaphore:
                return await process(page_number)

        results = await asyncio.gather(
            *(limited(page_number) for page_number in range(1, inspected.page_count + 1))
        )
        for result in results:
            pages.append(result.markdown)
            usage["input_tokens"] += result.input_tokens
            usage["output_tokens"] += result.output_tokens
            usage["cached_input_tokens"] += result.cached_input_tokens

    candidate = PAGE_BREAK.join(pages)
    accuracy = compare_markdown_accuracy(
        candidate,
        expected,
        candidate_types=classify_markdown_types(candidate),
        expected_types=classify_markdown_types(expected),
    )
    gates = {
        "overall": accuracy["overall"]["strict_word_accuracy"] >= ACCURACY_GATE,
        "every_page": accuracy["minimums"]["page_accuracy"] >= ACCURACY_GATE,
        "every_type": accuracy["minimums"]["type_accuracy"] >= ACCURACY_GATE,
    }
    report = {
        "source_sha256": source_sha256,
        "mode": mode.value,
        "gate": ACCURACY_GATE,
        "passed": all(gates.values()),
        "gates": gates,
        "landingai": accuracy,
        "peer": compare_markdown_accuracy(candidate, peer) if peer is not None else None,
        "usage": usage,
    }
    args.candidate_markdown.write_text(candidate, encoding="utf-8")
    args.report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--peer", type=Path)
    parser.add_argument("--candidate-markdown", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(parse_args())), indent=2))
