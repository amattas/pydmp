# aviato:managed profile=python-library version=2.0.1
# aviato:hash=2984c8b448f4db331def91bc2b94e5d48636803bb73503f3f4b08d87e2bfc5e9
# aviato:inputs=fc765bd1af8b69911f2d2f19fa83781590b443d64723218e325418c024d742fc
#!/usr/bin/env python3
"""Derive the next SemVer from Conventional Commits (Aviato §5.9 release logic).

MANAGED FILE — Aviato materializes this under `.github/aviato/` and re-renders it
every sync; do not hand-edit. It is a standalone, dependency-free copy of the
`aviato.core.versioning` release-derivation logic so the release workflow can run
it as `python .github/aviato/next-version.py` WITHOUT installing the Aviato
package (Phase 3 decision 6). `aviato validate` runs this script against a battery
of cases and fails if it drifts from `aviato.core.versioning`, so this copy can
never diverge silently from the engine it mirrors.
"""

from __future__ import annotations

import argparse
import re
import sys

_HEADER_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?P<scope>\([^)]*\))?(?P<bang>!)?:")
_RELEASE_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta)(\d+))?$")

# SemVer bump levels, ordered so the highest wins. 0 = no release.
_NONE, _PATCH, _MINOR, _MAJOR = 0, 1, 2, 3


def _has_breaking_footer(message: str) -> bool:
    return any(line.startswith(("BREAKING CHANGE:", "BREAKING-CHANGE:")) for line in message.splitlines())


def _commit_bump(message: str) -> int:
    header = message.lstrip().splitlines()[0] if message.strip() else ""
    match = _HEADER_RE.match(header.strip())
    if match is None:
        return _NONE
    if match.group("bang") or _has_breaking_footer(message):
        return _MAJOR
    commit_type = match.group("type").lower()
    if commit_type == "feat":
        return _MINOR
    if commit_type in ("fix", "perf"):
        return _PATCH
    return _NONE


def classify_commits(commits: list[str]) -> int:
    highest = _NONE
    for message in commits:
        bump = _commit_bump(message)
        if bump > highest:
            highest = bump
    return highest


def next_version(current: str, bump: int) -> str:
    match = _RELEASE_RE.match(current.strip())
    if match is None:
        raise ValueError(f"not a release version: {current!r}")
    major, minor, patch, pre, pre_num = match.groups()
    major, minor, patch = int(major), int(minor), int(patch)
    if bump == _MAJOR:
        return f"{major + 1}.0.0"
    if bump == _MINOR:
        return f"{major}.{minor + 1}.0"
    if bump == _PATCH:
        return f"{major}.{minor}.{patch + 1}"
    suffix = f"-{pre}{pre_num}" if pre is not None else ""
    return f"{major}.{minor}.{patch}{suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive the next SemVer from Conventional Commits.")
    parser.add_argument("--current", required=True, help="Current version (X.Y.Z or X.Y.Z-alphaN/-betaN).")
    parser.add_argument("--commit", action="append", help="A commit message (repeatable); else stdin.")
    args = parser.parse_args(argv)

    commits = list(args.commit or [])
    if not commits:
        raw = sys.stdin.read()
        # `git log --format=%B%x00` NUL-terminates each record; every message after
        # the first arrives with a leading newline, so strip the record-separator noise.
        commits = [c.strip() for c in (raw.split("\0") if "\0" in raw else raw.split("\n\n")) if c.strip()]
    try:
        result = next_version(args.current, classify_commits(commits))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
