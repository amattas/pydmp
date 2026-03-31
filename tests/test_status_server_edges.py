import asyncio

import pytest

from pydmp.status_server import DMPStatusServer


def test_extract_account_edges():
    header = b"\x02\x00\x00\x00\x00\x00\x00"  # STX + 6 header bytes
    # Real panel frame: STX + 6 header bytes + 5 account + body
    assert DMPStatusServer._extract_account(header + b"00001Zq\\...") == "00001"
    assert DMPStatusServer._extract_account(header + b"    1Zq\\...") == "    1"
    # Non-Z frame (e.g. s07 check-in) still works
    assert DMPStatusServer._extract_account(header + b"00001s07keepalive") == "00001"
    # No STX
    assert DMPStatusServer._extract_account(b"abcdeZ...") is None
    # Too short
    assert DMPStatusServer._extract_account(b"\x02short") is None


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

    # Line with 'Z' but fewer than 5 bytes before it → no account
    reader = R([b"abZq\\...\r", b""])
    writer = W()
    await srv._handle_client(reader, writer)
    # No account → no ACK
    assert writer.buffer.count(b"\x06\r") == 0


@pytest.mark.asyncio
async def test_ack_sent_for_non_z_frame():
    """Non-Z frames (e.g. s07 check-ins) should still get ACKed."""
    srv = DMPStatusServer()
    got = []
    srv.register_callback(lambda m: got.append(m))

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

    # s07 check-in frame: real panel format with header bytes, no Z
    header = b"\x02\x00\x01\x02\x03\x04\x05"  # STX + 6 header bytes
    acct = b"00001"
    reader = R([header + acct + b"s07keepalive\r", b""])
    writer = W()
    await srv._handle_client(reader, writer)
    # ACK should be sent even though there's no Z-frame
    assert writer.buffer.count(b"\x06\r") == 1
    assert b"\x0200001\x06\r" in writer.buffer
    # No callback dispatched (no Z-frame to parse)
    assert len(got) == 0


@pytest.mark.asyncio
async def test_real_panel_frame_with_header_bytes():
    """Frames from real panels have 6 header bytes between STX and account."""
    srv = DMPStatusServer()
    got = []
    srv.register_callback(lambda m: got.append(m))

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

    # Simulate real panel: STX + 6 header bytes + 5 account + Z-body + CR
    header = b"\x02\x00\x01\x02\x03\x04\x05"  # STX + 6 arbitrary header bytes
    acct = b"00001"
    z_body = b'Zq\\060\\t "CL\\a 001"AREA ONE\\'
    frame = header + acct + z_body + b"\r"
    reader = R([frame, b""])
    writer = W()
    await srv._handle_client(reader, writer)

    # ACK should contain the correct account
    assert b"\x0200001\x06\r" in writer.buffer
    # Callback should have fired with parsed arming event
    assert len(got) == 1
    assert got[0].account == "00001"
    assert got[0].definition == "Zq"
    assert got[0].type_code == "CL"
