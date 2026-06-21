#!/usr/bin/env python3
"""Release script — bump version, tag, push, and publish a GitHub release.

This is a small, well-tested wrapper around the release workflow
described in RELEASE.md. It enforces two things the manual flow is
prone to forget:

1. **All three version strings stay in sync** (pyproject.toml,
   backend/app/main.py, CHANGELOG.md).
2. **The tag is created from the release commit, not from a
   dirty working tree** (so the published source matches the tag).

Usage
-----

    # Dry run — print the plan, do nothing.
    python scripts/release.py --dry-run --bump patch --notes "..."

    # Cut a release on the current main, run the full pipeline.
    python scripts/release.py --bump patch --push --notes-file notes.md

    # Generate a release notes draft from conventional commits since
    # the last tag, then ask for confirmation before publishing.
    python scripts/release.py --bump minor --push

Arguments
---------

    --bump {major,minor,patch}    Semver component to bump.
    --version X.Y.Z              Set the version explicitly.
    --title "vX.Y.Z — title"     Release title (otherwise derived).
    --notes "..."                 Inline release notes.
    --notes-file PATH             Release notes from a file.
    --target BRANCH               Branch to tag (default: main).
    --push                        Push branch + tag, create GH release.
    --remote NAME                 Git remote (default: origin).
    --dry-run                     Print the plan, do not write.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
MAIN_PY = REPO_ROOT / "backend" / "app" / "main.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and return the result. Exit on failure by default."""
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        sys.stderr.write(f"Command failed ({result.returncode}): {' '.join(cmd)}\n")
        if result.stderr:
            sys.stderr.write(result.stderr)
        sys.exit(result.returncode)
    return result


def read_current_version() -> str:
    text = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    if not match:
        sys.exit("Could not find version in pyproject.toml")
    return match.group(1)


def bump(version: str, part: str) -> str:
    match = SEMVER_RE.match(version)
    if not match:
        sys.exit(f"Invalid version: {version!r}")
    major, minor, patch = (int(g) for g in match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    sys.exit(f"Unknown bump target: {part!r}")


def update_pyproject(new_version: str, dry: bool) -> None:
    text = PYPROJECT.read_text()
    new_text = re.sub(
        r'^(version\s*=\s*")\d+\.\d+\.\d+(")',
        rf"\g<1>{new_version}\g<2>",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if dry:
        print(f"  would set pyproject.toml version -> {new_version}")
    else:
        PYPROJECT.write_text(new_text)


def update_main_py(new_version: str, dry: bool) -> None:
    text = MAIN_PY.read_text()
    new_text = re.sub(
        r'(version=")\d+\.\d+\.\d+(")',
        rf"\g<1>{new_version}\g<2>",
        text,
        count=1,
    )
    if dry:
        print(f"  would set backend/app/main.py version -> {new_version}")
    else:
        MAIN_PY.write_text(new_text)


def update_changelog(new_version: str, notes: str, dry: bool) -> None:
    """Replace the [Unreleased] block with a dated [X.Y.Z] section.

    If the existing CHANGELOG has an empty [Unreleased] stub, drop it.
    Otherwise, move any content currently in [Unreleased] into the new
    dated section and add a fresh empty [Unreleased] block on top.
    """
    today = _dt.date.today().isoformat()
    text = CHANGELOG.read_text()
    section_header = f"## [{new_version}] - {today}"

    if "## [Unreleased]" in text:
        # Extract existing Unreleased content.
        unreleased_re = re.compile(
            r"## \[Unreleased\]\n(.*?)(?=\n## |\Z)",
            re.DOTALL,
        )
        match = unreleased_re.search(text)
        existing = match.group(1).strip() if match else ""
        if not existing:
            # Empty stub — just remove it.
            text = re.sub(
                r"## \[Unreleased\]\n+(?=\n## )",
                "",
                text,
                count=1,
            )
        else:
            # Promote Unreleased content into the new dated section.
            text = text.replace(
                "## [Unreleased]\n",
                "## [Unreleased]\n\n### Added\n\n### Changed\n\n### Fixed\n\n",
                1,
            )
            # Insert the dated section between Unreleased and the rest.
            new_block = f"## [Unreleased]\n\n## [{new_version}] - {today}\n\n{existing}\n\n"
            text = re.sub(
                r"## \[Unreleased\]\n+",
                new_block,
                text,
                count=1,
            )

    if notes:
        # Append release notes under the new version's section.
        insertion = f"\n\n### Release notes\n\n{notes.strip()}\n"
        if section_header in text:
            text = text.replace(section_header, section_header + insertion, 1)
        else:
            text += f"\n{section_header}{insertion}\n"

    if dry:
        print(f"  would update CHANGELOG.md for {new_version} ({today})")
    else:
        CHANGELOG.write_text(text)


def git(*args: str, check: bool = True) -> str:
    result = run(["git", *args], check=check, capture=True)
    return (result.stdout or "").strip()


def assert_clean_working_tree() -> None:
    status = git("status", "--porcelain")
    if status:
        sys.exit("Working tree is dirty. Commit or stash changes before releasing.\n" + status)


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")


def last_tag() -> str | None:
    out = git("tag", "--sort=-creatordate")
    return out.splitlines()[0] if out else None


def commits_since(ref: str | None) -> list[str]:
    rng = f"{ref}..HEAD" if ref else "HEAD"
    out = git("log", rng, "--pretty=format:%h %s", "--no-merges")
    return [line for line in out.splitlines() if line]


def derive_notes(commits: list[str]) -> str:
    if not commits:
        return "_No commits since last tag._"
    lines = ["### Changes", ""]
    for c in commits:
        lines.append(f"- {c}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Cut a versioned GitHub release.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--bump", choices=("major", "minor", "patch"))
    p.add_argument("--version", help="Set the version explicitly (e.g. 0.3.0).")
    p.add_argument("--title", help="Release title (default: vX.Y.Z — auto)")
    p.add_argument("--notes", help="Inline release notes.")
    p.add_argument("--notes-file", type=Path, help="Release notes from a file.")
    p.add_argument("--target", default="main", help="Branch to tag.")
    p.add_argument("--push", action="store_true", help="Push and publish.")
    p.add_argument("--remote", default="origin", help="Git remote name.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan, do not modify anything.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not args.bump and not args.version:
        sys.exit("Provide --bump {major,minor,patch} or --version X.Y.Z")

    current = read_current_version()
    new_version = args.version or bump(current, args.bump)
    if not SEMVER_RE.match(new_version):
        sys.exit(f"Invalid new version: {new_version!r}")

    if (
        SEMVER_RE.match(new_version)
        and SEMVER_RE.match(current)
        and [int(x) for x in new_version.split(".")] < [int(x) for x in current.split(".")]
    ):
        sys.exit(f"New version {new_version} is lower than current {current}.")

    notes = ""
    if args.notes_file:
        notes = args.notes_file.read_text()
    elif args.notes:
        notes = args.notes
    else:
        # Auto-derive a first draft from the commits since the last tag.
        notes = derive_notes(commits_since(last_tag()))

    title = args.title or f"v{new_version}"

    print("Release plan")
    print("------------")
    print(f"  current version : {current}")
    print(f"  new version     : v{new_version}")
    print(f"  target branch   : {args.target}")
    print(f"  current branch  : {current_branch()}")
    print(f"  remote          : {args.remote}")
    print(f"  title           : {title}")
    print(f"  push / publish  : {args.push}")
    print()
    print("Files to update")
    print("---------------")
    print(f"  - {PYPROJECT.relative_to(REPO_ROOT)}")
    print(f"  - {MAIN_PY.relative_to(REPO_ROOT)}")
    print(f"  - {CHANGELOG.relative_to(REPO_ROOT)}")
    print()
    print("Notes (first 400 chars)")
    print("-----------------------")
    print(notes[:400] + ("…" if len(notes) > 400 else ""))
    print()

    if args.dry_run:
        print("Dry run — no changes written.")
        return 0

    if args.push:
        assert_clean_working_tree()
        if current_branch() != args.target:
            print(
                f"Warning: you are on {current_branch()!r}, not {args.target!r}. Continuing anyway."
            )

    update_pyproject(new_version, dry=False)
    update_main_py(new_version, dry=False)
    update_changelog(new_version, notes, dry=False)

    if args.push:
        # Commit, tag, push.
        git("add", "pyproject.toml", "backend/app/main.py", "CHANGELOG.md")
        commit_msg = f"chore(release): {new_version}"
        git("commit", "-m", commit_msg)
        tag = f"v{new_version}"
        git("tag", "-a", tag, "-m", title)
        git("push", args.remote, args.target)
        git("push", args.remote, tag)
        # Create the GitHub release if `gh` is available.
        gh = subprocess.run(
            [
                "gh",
                "release",
                "create",
                tag,
                "--title",
                title,
                "--notes",
                notes,
                "--target",
                args.target,
            ],
            cwd=REPO_ROOT,
            text=True,
        )
        if gh.returncode != 0:
            print(
                "`gh release create` failed — the tag and commits are pushed, "
                "but the GitHub release was not created. You can run it manually:\n"
                f"  gh release create {tag} --title {title!r} --target {args.target}"
            )
            return gh.returncode
        print(f"Published {tag}: https://github.com/{_detect_repo()}/releases/tag/{tag}")
    else:
        print("Files updated. Run with --push to commit, tag, and publish.")

    return 0


def _detect_repo() -> str:
    out = git("remote", "get-url", "origin")
    if out.startswith("git@"):
        out = out.split(":", 1)[1]
    elif "://" in out:
        out = out.split("://", 1)[1]
    return out.removesuffix(".git")


if __name__ == "__main__":
    raise SystemExit(main())
