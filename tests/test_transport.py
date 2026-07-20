import asyncio
import logging

import pytest

from pydmp.exceptions import DMPConnectionError, DMPTimeoutError
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


@pytest.mark.asyncio
async def test_send_raw_redacts_remote_key(monkeypatch, caplog):
    async def fake_open_connection(host, port):
        return _FakeReader([b""]), _FakeWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    t = DMPTransport("example", 1234, timeout=1.0)
    await t.connect()
    with caplog.at_level(logging.DEBUG, logger="pydmp.transport"):
        await t._send_raw(b"@    1!V2S3CRETKEY\r")
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "S3CRETKEY" not in logged
    assert "!V2<redacted>" in logged
    # Non-sensitive frames still log their content.
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="pydmp.transport"):
        await t._send_raw(b"@    1!S\r")
    assert "!S" in " ".join(r.getMessage() for r in caplog.records)
    await t.disconnect()


@pytest.mark.asyncio
async def test_transport_connect_timeouts(monkeypatch):
    async def raise_timeout(host, port):
        raise TimeoutError()

    monkeypatch.setattr(asyncio, "open_connection", raise_timeout)
    t = DMPTransport("h", 1, timeout=0.01)
    with pytest.raises(DMPTimeoutError):
        await t.connect()


@pytest.mark.asyncio
async def test_transport_connect_oserror(monkeypatch):
    async def raise_oserror(host, port):
        raise OSError("no route")

    monkeypatch.setattr(asyncio, "open_connection", raise_oserror)
    t = DMPTransport("h", 1, timeout=0.01)
    with pytest.raises(DMPConnectionError):
        await t.connect()


class _R:
    async def read(self, n):  # noqa: D401
        # Simulate a long read that times out quickly inside this coroutine
        await asyncio.wait_for(asyncio.sleep(10), timeout=0.01)
        return b"data"


@pytest.mark.asyncio
async def test_receive_timeout_breaks_loop(monkeypatch):
    t = DMPTransport("h", 1, timeout=0.01)
    # Install reader directly; no need to connect
    t._reader = _R()  # type: ignore[attr-defined]
    # Speed up rate limiting sleep
    import pydmp.transport as tr

    monkeypatch.setattr(tr, "RATE_LIMIT_SECONDS", 0)
    data = await t._receive()
    assert data == b""
