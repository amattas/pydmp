import asyncio

import pytest

from pydmp.const.commands import DMPCommand
from pydmp.panel import DMPPanel


class _DummyProtocol:
    def encode_command(self, cmd: str, **kwargs) -> bytes:  # noqa: D401
        return b"KA" if cmd == DMPCommand.KEEP_ALIVE.value else b"X"

    def decode_response(self, data: bytes):  # noqa: D401
        return None


class _DummyTransport:
    def __init__(self):
        self.is_connected = True
        self.sent: list[bytes] = []

    async def send_and_receive(self, data: bytes) -> bytes:  # noqa: D401
        self.sent.append(bytes(data))
        return b""  # no response expected


@pytest.mark.asyncio
async def test_keepalive_start_stop():
    p = DMPPanel()
    # inject protocol and transport
    p._protocol = _DummyProtocol()  # type: ignore[attr-defined]
    p._connection = _DummyTransport()  # type: ignore[attr-defined]

    await p.start_keepalive(interval=0.01)
    # let a couple of iterations happen
    await asyncio.sleep(0.05)
    await p.stop_keepalive()

    # ensure at least one KA went out
    assert isinstance(p._connection, _DummyTransport)
    assert len(p._connection.sent) >= 1


@pytest.mark.asyncio
async def test_keepalive_idempotent(monkeypatch):
    p = DMPPanel()
    p._protocol = _DummyProtocol()  # type: ignore[attr-defined]
    p._connection = _DummyTransport()  # type: ignore[attr-defined]

    # starting twice should not raise and should keep sending
    await p.start_keepalive(interval=0.01)
    await p.start_keepalive(interval=0.01)
    await asyncio.sleep(0.03)
    await p.stop_keepalive()
    assert isinstance(p._connection, _DummyTransport)
    assert len(p._connection.sent) >= 1
