"""Shared test scaffolding for the pydmp test suite."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


class FakeReader:
    """Minimal async reader that yields pre-chunked byte payloads."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, n: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class FakeWriter:
    """Minimal async writer that records everything written to it."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def get_extra_info(self, name: str) -> Any:
        return ("127.0.0.1", 0)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        await asyncio.sleep(0)


def frame_with_header(account: bytes, z_body: bytes) -> bytes:
    """Build a real-panel-shaped S3 frame: STX + 6 header bytes + account + body + CR."""
    header = b"\x02\x00\x00\x00\x00\x00\x00"
    return header + account + z_body + b"\r"


class FakePanelConnection:
    """Minimal stand-in for a live panel connection used by DMPPanel tests.

    Exposes ``is_connected`` (so ``DMPPanel`` treats itself as connected) plus
    a scripted ``send_command`` that pops canned responses off a queue,
    falling back to ``"ACK"`` once the queue is exhausted. Also provides a
    no-op ``keep_alive`` for tests that exercise the keepalive loop through a
    real connection object rather than a dummy transport.
    """

    def __init__(
        self,
        responses: list[Any] | None = None,
        *,
        host: str = "h",
        port: int = 0,
        account: str = "a",
    ) -> None:
        self.is_connected = True
        self._responses = list(responses or [])
        self.calls: list[tuple[str, dict]] = []
        self.host = host
        self.port = port
        self.account = account

    async def send_command(self, cmd: str, **kwargs: Any) -> Any:
        self.calls.append((cmd, kwargs))
        if self._responses:
            return self._responses.pop(0)
        return "ACK"

    async def keep_alive(self) -> None:
        self.calls.append(("!H", {}))


def install_fake_transport(
    monkeypatch: Any, fake_transport_cls: type, fake_protocol_cls: type
) -> None:
    """Patch ``pydmp.panel``'s transport/protocol classes with fakes for connect()."""
    import pydmp.panel as panel_mod

    monkeypatch.setattr(panel_mod, "DMPTransport", fake_transport_cls)
    monkeypatch.setattr(panel_mod, "DMPProtocol", fake_protocol_cls)


def make_user_code(
    code: str = "1234", pin: str = "", number: str = "0001", name: str = "USER"
) -> Any:
    """Build a ``UserCode`` with sensible defaults, for cache/check_code tests."""
    from pydmp.user import UserCode

    return UserCode(
        number=number,
        code=code,
        pin=pin,
        profiles=("001", "002", "003", "004"),
        temp_date="010125",
        exp_date="0900",
        name=name,
    )


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
            p.write_text(
                f"host: h\naccount: '1'\nremote_key: 'K'\nport: {port}\ntimeout: {timeout}\n"
            )
        else:
            p.write_text(
                "panel:\n  host: h\n  account: '1'\n  remote_key: 'K'\n"
                f"  port: {port}\n  timeout: {timeout}\n"
            )
        return p

    return _make


class MinimalPanel:
    """Minimal no-op fake ``DMPPanel`` for CLI tests.

    Provides no-op ``connect``/``disconnect`` and an ACK-returning ``_send_command``.
    Subclass and override individual methods to script the behavior a given test needs.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def connect(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def _send_command(self, *args: Any, **kwargs: Any) -> str:
        return "ACK"
