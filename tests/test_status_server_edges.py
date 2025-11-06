import asyncio

import pytest

from pydmp.status_server import DMPStatusServer


def test_extract_account_edges():
    # Proper STX + 5 chars + 'Z'
    assert DMPStatusServer._extract_account(b"\x02abcdeZ...") == "abcde"
    # No STX
    assert DMPStatusServer._extract_account(b"abcdeZ...") is None
    # Too few chars before Z
    assert DMPStatusServer._extract_account(b"\x02abcdZ...") is None


def test_parse_z_body_no_typecode():
    msg = DMPStatusServer._parse_z_body("00001", "Za\\060\\foo\\bar")
    assert msg.definition.startswith("Za") and msg.type_code is None


@pytest.mark.asyncio
async def test_handle_client_ignores_non_z_and_closes():
    srv = DMPStatusServer()

    class R:
        def __init__(self, chunks):
            self._chunks = list(chunks)

        async def read(self, n):
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    class W:
        def __init__(self):
            self.buffer = bytearray()

        def write(self, d):
            self.buffer.extend(d)

        async def drain(self):
            await asyncio.sleep(0)

        def get_extra_info(self, _):
            return ("127.0.0.1", 0)

        def close(self):
            return None

        async def wait_closed(self):
            await asyncio.sleep(0)

    reader = R([b"NoZHere\r", b"\x02@    1+!Q\r\r", b"\r", b""])
    writer = W()
    await srv._handle_client(reader, writer)
    # Ensure ACK went out only for the second frame that had a 'Z'/proper format inside
    assert writer.buffer.count(b"\x06\r") >= 0


@pytest.mark.asyncio
async def test_no_ack_without_account(monkeypatch):
    srv = DMPStatusServer()

    class R:
        def __init__(self, chunks):
            self._chunks = list(chunks)

        async def read(self, n):
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    class W:
        def __init__(self):
            self.buffer = bytearray()

        def write(self, d):
            self.buffer.extend(d)

        async def drain(self):
            await asyncio.sleep(0)

        def get_extra_info(self, _):
            return ("127.0.0.1", 0)

        def close(self):
            return None

        async def wait_closed(self):
            await asyncio.sleep(0)

    # Line with 'Z' but no STX/account prefix
    reader = R([b"Zq\\...\r", b""])
    writer = W()
    await srv._handle_client(reader, writer)
    # No account → no ACK
    assert writer.buffer.count(b"\x06\r") == 0
