"""Package import smoke test (seed-once; the developer owns and extends this file)."""

import pydmp


def test_package_imports() -> None:
    assert pydmp.__name__ == "pydmp"
