"""Opt-in live parse canary; never runs in the offline test suite."""

from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def validated_base_url(value: str, *, allow_remote: bool) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Base URL must be an HTTP(S) origin without a path")
    try:
        is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        is_loopback = parsed.hostname.casefold() == "localhost"
    if not is_loopback and not allow_remote:
        raise ValueError("Remote canary targets require --allow-remote")
    if not is_loopback and parsed.scheme != "https":
        raise ValueError("Remote canary targets must use HTTPS")
    return value.rstrip("/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args()
    base_url = validated_base_url(args.base_url, allow_remote=args.allow_remote)
    api_key = os.environ.get("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}
    with args.document.open("rb") as source:
        response = httpx.post(
            f"{base_url}/v2/parse",
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
