import asyncio

import pytest

from pydmp.exceptions import DMPConnectionError
from pydmp.transport import DMPTransport


class _FakeReader(asyncio.StreamReader):
    def __init__(self, chunks: list[bytes]):
        super().__init__()
        self._chunks = list(chunks)

    async def read(self, n: int) -> bytes:  # type: ignore[override]
        await asyncio.sleep(0)
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _FakeWriter:
    def __init__(self):
        self.buffer = bytearray()
        self._closed = False

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def is_closing(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        await asyncio.sleep(0)

    def get_extra_info(self, name: str):  # for symmetry with real writer
        return None


@pytest.mark.asyncio
async def test_transport_connect_send_receive(monkeypatch):
    async def fake_open_connection(host, port):
        return _FakeReader([b"part1", b"part2", b"\r", b""]), _FakeWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    t = DMPTransport("example", 1234, timeout=1.0)
    await t.connect()
    assert t.is_connected

    data = await t.send_and_receive(b"PING")
    # All chunks concatenated
    assert data.startswith(b"part1part2")

    await t.disconnect()
    assert not t.is_connected


@pytest.mark.asyncio
async def test_transport_send_without_connect_raises():
    t = DMPTransport("example", 1234, timeout=1.0)
    with pytest.raises(DMPConnectionError):
        await t.send_and_receive(b"PING")
