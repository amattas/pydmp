"""Shared test scaffolding for the pydmp test suite."""

from __future__ import annotations

import asyncio
from typing import Any


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
        self, responses: list[Any] | None = None, *, host: str = "h", port: int = 0, account: str = "a"
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


def install_fake_transport(monkeypatch: Any, fake_transport_cls: type, fake_protocol_cls: type) -> None:
    """Patch ``pydmp.panel``'s transport/protocol classes with fakes for connect()."""
    import pydmp.panel as panel_mod

    monkeypatch.setattr(panel_mod, "DMPTransport", fake_transport_cls)
    monkeypatch.setattr(panel_mod, "DMPProtocol", fake_protocol_cls)


def make_user_code(code: str = "1234", pin: str = "", number: str = "0001", name: str = "USER") -> Any:
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
