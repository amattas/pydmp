import asyncio

import pytest

from pydmp.exceptions import DMPConnectionError, DMPTimeoutError
from pydmp.transport import DMPTransport


@pytest.mark.asyncio
async def test_transport_connect_timeouts(monkeypatch):
    async def raise_timeout(host, port):
        raise asyncio.TimeoutError()

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
