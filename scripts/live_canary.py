"""Opt-in live parse canary; never runs in the offline test suite."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    api_key = os.environ.get("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}
    with args.document.open("rb") as source:
        response = httpx.post(
            f"{args.base_url.rstrip('/')}/v2/parse",
            headers=headers,
            files={"file": (args.document.name, source)},
            data={"model": "paperplane-ade-fast-latest"},
            timeout=600,
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("markdown") or not payload.get("metadata", {}).get("job_id"):
        raise RuntimeError("Canary response is missing Markdown or job metadata")
    print(f"live canary passed: job={payload['metadata']['job_id']}")


if __name__ == "__main__":
    main()
