import asyncio

import pytest

from pydmp.status_server import DMPStatusServer


@pytest.mark.asyncio
async def test_ack_count_multiple_frames():
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

    # Two valid Z frames: STX + 6 header bytes + account + Z-body + CR
    header = b"\x02\x00\x00\x00\x00\x00\x00"
    acct = b"00001"
    z1 = header + acct + b"Zq\\...\r"
    z2 = header + acct + b"Za\\...\r"
    reader = R([z1 + z2, b""])
    writer = W()
    await srv._handle_client(reader, writer)
    assert writer.buffer.count(b"\x06\r") == 2
