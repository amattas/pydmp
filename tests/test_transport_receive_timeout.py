import asyncio

import pytest

from pydmp.transport import DMPTransport


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
