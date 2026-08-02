# aviato:managed profile=python-library version=2.5.1
# aviato:hash=9d6da5266f95e5eec6dc06812a410b896c234f4f76436683ded347fad6b773c5
# aviato:inputs=fc765bd1af8b69911f2d2f19fa83781590b443d64723218e325418c024d742fc
#!/usr/bin/env python3
"""Exit 0 iff CANDIDATE is the highest released version (Aviato §8.14 alias guard).

MANAGED FILE — Aviato materializes this under `.github/aviato/` and re-renders it
every sync; do not hand-edit. It is a standalone, dependency-free copy of
`aviato.core.versioning.is_highest` so the release workflow can gate the mutable
floating-major pointer as `python .github/aviato/is-highest.py` WITHOUT installing
the Aviato package (Phase 3 decision 6). `aviato validate` runs this script
against a battery of cases and fails if it drifts from `aviato.core.versioning`.
"""

from __future__ import annotations

import re
import sys

_RELEASE_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta)(\d+))?$")
# Pre-release rank: a final release outranks beta, which outranks alpha.
_PRE_RANK = {None: 2, "beta": 1, "alpha": 0}


def _release_key(tag: str) -> tuple[int, int, int, int, int] | None:
    match = _RELEASE_RE.match(tag.strip())
    if match is None:
        return None
    major, minor, patch, pre, pre_num = match.groups()
    return (int(major), int(minor), int(patch), _PRE_RANK[pre], int(pre_num or 0))


def is_highest(candidate: str, existing: list[str]) -> bool:
    candidate_key = _release_key(candidate)
    if candidate_key is None:
        return False
    keys = [key for key in (_release_key(tag) for tag in existing) if key is not None]
    keys.append(candidate_key)
    return max(keys) == candidate_key


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: is-highest.py CANDIDATE [EXISTING ...]", file=sys.stderr)
        return 2
    candidate, existing = args[0], args[1:]
    if _release_key(candidate) is None:
        print(
            f"is-highest: candidate {candidate!r} is not a parseable version (treated as not highest)",
            file=sys.stderr,
        )
    return 0 if is_highest(candidate, existing) else 1


if __name__ == "__main__":
    raise SystemExit(main())
