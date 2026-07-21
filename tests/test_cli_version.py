from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

import pydmp
import pydmp.cli as cli
from pydmp import __version__


def test_cli_version_short_flag() -> None:
    r = CliRunner().invoke(cli.cli, ["-v"])  # short version flag
    assert r.exit_code == 0
    assert __version__ in r.output


def test_runtime_version_unreadable_pyproject_raises_runtime_error(monkeypatch: Any) -> None:
    def _no_dist(name: Any) -> None:
        raise PackageNotFoundError(name)

    def _no_read(self: Path, *args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError(self)

    monkeypatch.setattr(pydmp, "_dist_version", _no_dist)
    monkeypatch.setattr(Path, "read_text", _no_read)
    with pytest.raises(RuntimeError, match="version"):
        pydmp._runtime_version()
