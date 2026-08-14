#!/usr/bin/env python3
"""Version, tag, and publish a source-only Paperplane GitHub release."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
STREAMLIT_APP = ROOT / "streamlit_app.py"
CHANGELOG = ROOT / "CHANGELOG.md"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def command(*parts: str, capture: bool = False) -> str:
    result = subprocess.run(
        list(parts),
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def current_version() -> str:
    match = re.search(
        r'^version\s*=\s*"(\d+\.\d+\.\d+)"',
        PYPROJECT.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        raise SystemExit("Could not find the project version")
    return match.group(1)


def next_version(current: str, part: str) -> str:
    match = SEMVER.fullmatch(current)
    if match is None:
        raise SystemExit(f"Invalid current version: {current}")
    major, minor, patch = (int(value) for value in match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def replace_version(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"Could not update {path.relative_to(ROOT)}")
    path.write_text(updated, encoding="utf-8")


def add_changelog(version: str, notes: str) -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    heading = f"## [{version}] - {dt.date.today().isoformat()}"
    if heading in text:
        return
    body = notes.strip() or "- Source release."
    marker = "## [Unreleased]"
    replacement = f"{marker}\n\n### Added\n\n### Changed\n\n### Fixed\n\n{heading}\n\n{body}"
    text = re.sub(
        r"## \[Unreleased\].*?(?=\n## \[)",
        replacement,
        text,
        count=1,
        flags=re.DOTALL,
    )
    CHANGELOG.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--bump", choices=("major", "minor", "patch"))
    target.add_argument("--version")
    parser.add_argument("--notes", default="")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    current = current_version()
    version = args.version or next_version(current, args.bump)
    if SEMVER.fullmatch(version) is None:
        raise SystemExit(f"Invalid semantic version: {version}")

    print(f"Paperplane {current} -> {version}")
    print("Updates: pyproject.toml, uv.lock, streamlit_app.py, CHANGELOG.md")
    print(f"Publish: {args.push}")
    if args.dry_run:
        return 0
    if args.push and command("git", "status", "--porcelain", capture=True).strip():
        raise SystemExit("Working tree must be clean before --push")

    replace_version(
        PYPROJECT,
        r'^(version\s*=\s*")\d+\.\d+\.\d+(")',
        rf"\g<1>{version}\g<2>",
    )
    replace_version(
        STREAMLIT_APP,
        r'^(APP_VERSION\s*=\s*")\d+\.\d+\.\d+(")',
        rf"\g<1>{version}\g<2>",
    )
    add_changelog(version, args.notes)
    command("uv", "lock")

    if not args.push:
        return 0
    command(
        "git",
        "add",
        "pyproject.toml",
        "uv.lock",
        "streamlit_app.py",
        "CHANGELOG.md",
    )
    command("git", "commit", "-m", f"chore(release): {version}")
    tag = f"v{version}"
    command("git", "tag", "-a", tag, "-m", tag)
    command("git", "push", "origin", "main")
    command("git", "push", "origin", tag)
    command("gh", "release", "create", tag, "--title", tag, "--notes", args.notes or tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
