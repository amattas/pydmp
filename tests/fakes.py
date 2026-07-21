"""Typed reusable test doubles for the pydmp test suite."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from pydmp.panel import DMPPanel
from pydmp.protocol import DMPProtocol
from pydmp.transport import DMPTransport
from pydmp.user import UserCode


class FakeReader:
    """Minimal async reader that yields pre-chunked byte payloads."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, n: int = -1) -> bytes:
        del n
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
        del name
        return ("127.0.0.1", 0)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        await asyncio.sleep(0)


def as_stream_reader(fake: FakeReader) -> asyncio.StreamReader:
    """Cast a structurally compatible fake at a stream-reader boundary."""
    return cast(asyncio.StreamReader, fake)


def as_stream_writer(fake: FakeWriter) -> asyncio.StreamWriter:
    """Cast a structurally compatible fake at a stream-writer boundary."""
    return cast(asyncio.StreamWriter, fake)


def frame_with_header(account: bytes, z_body: bytes) -> bytes:
    """Build a real-panel-shaped S3 frame."""
    header = b"\x02\x00\x00\x00\x00\x00\x00"
    return header + account + z_body + b"\r"


class FakePanelConnection:
    """Scriptable stand-in for a live panel connection."""

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
        self.calls: list[tuple[str, dict[str, Any]]] = []
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


def cast_transport(fake: object) -> DMPTransport:
    """Cast a structurally compatible test transport at an injection boundary."""
    return cast(DMPTransport, fake)


def cast_protocol(fake: object) -> DMPProtocol:
    """Cast a structurally compatible test protocol at an injection boundary."""
    return cast(DMPProtocol, fake)


def cast_panel(fake: object) -> DMPPanel:
    """Cast a structurally compatible test panel at an injection boundary."""
    return cast(DMPPanel, fake)


def install_fake_transport(
    monkeypatch: pytest.MonkeyPatch,
    fake_transport_cls: type[Any],
    fake_protocol_cls: type[Any],
) -> None:
    """Patch pydmp.panel transport/protocol classes with test doubles."""
    import pydmp.panel as panel_mod

    monkeypatch.setattr(panel_mod, "DMPTransport", fake_transport_cls)
    monkeypatch.setattr(panel_mod, "DMPProtocol", fake_protocol_cls)


def make_user_code(
    code: str = "1234",
    pin: str = "",
    number: str = "0001",
    name: str = "USER",
) -> UserCode:
    """Build a UserCode with sensible defaults."""
    return UserCode(
        number=number,
        code=code,
        pin=pin,
        profiles=("001", "002", "003", "004"),
        temp_date="010125",
        exp_date="0900",
        name=name,
    )


class MinimalPanel:
    """Minimal no-op DMPPanel-compatible fake for CLI tests."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def connect(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def disconnect(self) -> None:
        return None

    async def _send_command(self, *args: Any, **kwargs: Any) -> str:
        del args, kwargs
        return "ACK"
