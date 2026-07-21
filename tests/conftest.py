"""Pytest fixtures and compatibility re-exports for shared test scaffolding."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from .fakes import (
    FakePanelConnection,
    FakeReader,
    FakeWriter,
    MinimalPanel,
    frame_with_header,
    install_fake_transport,
    make_user_code,
)

__all__ = [
    "FakePanelConnection",
    "FakeReader",
    "FakeWriter",
    "MinimalPanel",
    "frame_with_header",
    "install_fake_transport",
    "make_user_code",
]


@pytest.fixture
def cli_cfg(tmp_path: Path) -> Callable[..., Path]:
    """Factory fixture for writing a CLI config YAML file.

    Replaces the ``_cfg(tmp_path)`` / ``_cfg_top(tmp_path)`` helpers duplicated across
    CLI test files. Call with ``top_level=True`` for the unnested ("not under 'panel'")
    config shape used to exercise config normalization.
    """

    def _make(*, top_level: bool = False, port: int = 2011, timeout: float = 1) -> Path:
        p = tmp_path / "cfg.yaml"
        if top_level:
            p.write_text(f"host: h\naccount: '1'\nremote_key: 'K'\nport: {port}\ntimeout: {timeout}\n")
        else:
            p.write_text(
                f"panel:\n  host: h\n  account: '1'\n  remote_key: 'K'\n  port: {port}\n  timeout: {timeout}\n"
            )
        return p

    return _make
