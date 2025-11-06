import asyncio
import pytest

from pydmp.status_server import DMPStatusServer


@pytest.mark.asyncio
async def test_status_server_start_stop():
    # Use ephemeral port 0
    srv = DMPStatusServer(host="127.0.0.1", port=0)
    await srv.start()
    await srv.stop()


def test_extract_account_helper():
    from pydmp.status_server import DMPStatusServer as S

    good = b"\x02    1Zq\\...\r"
    assert S._extract_account(good) == "    1"

    bad = b"NoSTXHere"
    assert S._extract_account(bad) is None


class FakeReader:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, n):
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


@pytest.mark.asyncio
async def test_handle_client_multiple_lines():
    srv = DMPStatusServer()
    got = []
    srv.register_callback(lambda m: got.append(m))

    account = b"    1"
    line1 = b"\x02" + account + b"Za\\060\\t \"BU\\z 001\"Z1\\\r"
    line2 = b"\x02" + account + b"Zq\\060\\t \"OP\\a 01\"AREA\\\r"
    reader = FakeReader([line1 + line2, b""])  # both in one chunk
    writer = type("W", (), {"buffer": bytearray(), "write": lambda self, d: self.buffer.extend(d), "drain": (lambda self: asyncio.sleep(0)), "get_extra_info": lambda self, _: ("127.0.0.1", 0), "close": lambda self: None, "wait_closed": (lambda self: asyncio.sleep(0))})()

    await srv._handle_client(reader, writer)

    # Expect two callbacks and two ACK frames
    assert len(got) == 2
    assert writer.buffer.count(b"\x06\r") == 2
