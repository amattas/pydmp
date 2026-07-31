# aviato:managed profile=python-library version=2.2.0
# aviato:hash=1a2d0b39e8199e0d3578aa527215cfc66cd22c495f13814ce64adc4400510a21
# aviato:inputs=fc765bd1af8b69911f2d2f19fa83781590b443d64723218e325418c024d742fc
#!/usr/bin/env python3
"""Write a release version into the version-source location(s) (Aviato §3.3/§5.9).

MANAGED FILE — Aviato materializes this under `.github/aviato/` and re-renders it
every sync; do not hand-edit. It is a standalone, dependency-free copy of
`aviato.plugins.version_formats` (`bump_text`/`bump_files`) so the release
workflow can bump the version-source as `python .github/aviato/bump-version.py`
WITHOUT installing the Aviato package (Phase 3 decision 6). The per-profile
version-source path(s) are supplied on the command line by the flattened release
workflow. `aviato validate` runs this script against a battery of cases and fails
if it drifts from the engine rewriters it mirrors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_PYPROJECT_VERSION = re.compile(r'(?m)^(?P<prefix>version\s*=\s*)(?P<q>["\'])[^"\']*(?P=q)')
_PYPROJECT_VERSION_TABLES = ("project", "tool.poetry")
_PBXPROJ_MARKETING = re.compile(r"(MARKETING_VERSION\s*=\s*)[^;]+;")
_PBXPROJ_BUILD = re.compile(r"(CURRENT_PROJECT_VERSION\s*=\s*)[^;]+;")
_PLIST_SHORT = re.compile(r"(<key>CFBundleShortVersionString</key>\s*<string>)[^<]*(</string>)")
_PLIST_BUILD = re.compile(r"(<key>CFBundleVersion</key>\s*<string>)[^<]*(</string>)")


class BumpError(Exception):
    """A version-source file exists but could not be rewritten (fail closed)."""


def _bare(version: str) -> str:
    return version[1:] if version.startswith("v") else version


def _rewrite_toml_table_version(text: str, tables: tuple[str, ...], bare: str) -> tuple[str, int]:
    for table in tables:
        header = re.search(r"(?m)^\[" + re.escape(table) + r"\]\s*$", text)
        if header is None:
            continue
        start = header.end()
        following = re.search(r"(?m)^\[", text[start:])
        end = start + following.start() if following else len(text)
        segment, count = _PYPROJECT_VERSION.subn(
            lambda m: f"{m.group('prefix')}{m.group('q')}{bare}{m.group('q')}", text[start:end], count=1
        )
        if count:
            return text[:start] + segment + text[end:], count
    return text, 0


def _top_level_json_string_span(text: str, key: str) -> tuple[int, int] | None:
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            token = text[i + 1 : j]
            after = j + 1
            while after < n and text[after] in " \t\r\n":
                after += 1
            if depth == 1 and token == key and after < n and text[after] == ":":
                value = after + 1
                while value < n and text[value] in " \t\r\n":
                    value += 1
                if value < n and text[value] == '"':
                    w = value + 1
                    while w < n and text[w] != '"':
                        w += 2 if text[w] == "\\" else 1
                    return (value, w + 1)
                return None
            i = j + 1
            continue
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        i += 1
    return None


def bump_text(filename: str, text: str, new_version: str, build_number: str | None = None) -> str:
    """Rewrite the version string(s) in a version-source file's text (§3.3)."""
    name = Path(filename).name
    bare = _bare(new_version)

    if name == "VERSION":
        return f"{bare}\n"

    if name == "pyproject.toml":
        new, count = _rewrite_toml_table_version(text, _PYPROJECT_VERSION_TABLES, bare)
        if count == 0:
            raise BumpError(f"no [project]/[tool.poetry] version field found in {filename}")
        return new

    if name == "package.json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BumpError(f"{filename} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("version"), str):
            raise BumpError(f"no top-level version string found in {filename}")
        span = _top_level_json_string_span(text, "version")
        if span is None:
            raise BumpError(f"could not locate the top-level version field to rewrite in {filename}")
        return text[: span[0]] + f'"{bare}"' + text[span[1] :]

    if name.endswith(".pbxproj"):
        new, count = _PBXPROJ_MARKETING.subn(lambda m: f"{m.group(1)}{bare};", text)
        if count == 0:
            raise BumpError(f"no MARKETING_VERSION found in {filename}")
        if build_number is not None:
            new, build_count = _PBXPROJ_BUILD.subn(lambda m: f"{m.group(1)}{build_number};", new)
            if build_count == 0:
                raise BumpError(f"no CURRENT_PROJECT_VERSION found in {filename} to write build number")
        return new

    if name.endswith(".plist"):
        new, count = _PLIST_SHORT.subn(lambda m: f"{m.group(1)}{bare}{m.group(2)}", text)
        if count == 0:
            raise BumpError(f"no CFBundleShortVersionString found in {filename}")
        if build_number is not None:
            new, build_count = _PLIST_BUILD.subn(lambda m: f"{m.group(1)}{build_number}{m.group(2)}", new)
            if build_count == 0:
                raise BumpError(f"no CFBundleVersion found in {filename} to write build number")
        return new

    return text


def bump_files(locations: list[str], new_version: str, build_number: str | None = None) -> list[str]:
    """Bump the version in each existing version-source location (relative to cwd).

    Two passes: read + render EVERY present location (raising on any broken manifest
    BEFORE touching disk); only then write the changed ones (§2.5 never half-apply).
    Returns the list of files actually rewritten.
    """
    seen: set[str] = set()
    deduped: list[str] = []
    for loc in locations:
        if loc not in seen:
            seen.add(loc)
            deduped.append(loc)
    pending: list[tuple[str, str]] = []
    for location in deduped:
        path = Path(location)
        if not path.exists():
            continue
        if not path.is_file():
            raise BumpError(f"version-source location exists but is not a regular file, cannot bump: {location}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise BumpError(f"version-source file is not valid UTF-8, cannot bump: {location}") from exc
        except OSError as exc:
            raise BumpError(f"version-source file cannot be read, cannot bump: {location}: {exc}") from exc
        bumped = bump_text(location, text, new_version, build_number)
        if bumped != text:
            pending.append((location, bumped))
    changed: list[str] = []
    for location, bumped in pending:
        Path(location).write_text(bumped, encoding="utf-8")
        changed.append(location)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a release version into the version-source location(s).")
    parser.add_argument("version", help="Release version (X.Y.Z or X.Y.Z-alphaN/-betaN).")
    parser.add_argument("locations", nargs="+", help="Version-source file path(s) relative to the repo root.")
    parser.add_argument("--build-number", default=None, help="Strictly-increasing build number for app bundles.")
    args = parser.parse_args(argv)

    candidate = args.version.strip()
    bare = candidate[1:] if candidate.startswith("v") else candidate
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(alpha|beta)[0-9]+)?", bare):
        print(
            f"not a release version: {args.version!r} (expected X.Y.Z or X.Y.Z-alphaN/-betaN)",
            file=sys.stderr,
        )
        return 2

    present = [loc for loc in args.locations if Path(loc).is_file()]
    try:
        changed = bump_files(args.locations, bare, args.build_number)
    except BumpError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for location in changed:
        print(f"bumped {location} -> {bare}")
    if not present:
        print(
            f"no version-source file found among {args.locations}; set version_source.locations "
            "to your project's actual version file(s).",
            file=sys.stderr,
        )
        return 1
    if not changed:
        print(f"version-source already at {bare}; nothing to bump")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
