import asyncio

import pytest

from pydmp.panel import DMPPanel
from pydmp.protocol import StatusResponse


class FakeConn:
    def __init__(self, responses=None):
        self.is_connected = True
        self._responses = list(responses or [])
        self.host = "h"
        self.port = 0
        self.account = "a"

    async def send_command(self, cmd: str, **kwargs):
        if self._responses:
            return self._responses.pop(0)
        return "ACK"

    async def keep_alive(self):
        return None


@pytest.mark.asyncio
async def test_get_outputs_and_missing_area_zone():
    panel = DMPPanel()
    # Empty status response
    panel._connection = FakeConn([StatusResponse(areas={}, zones={})])

    # get_outputs creates 1..4
    outs = await panel.get_outputs()
    assert [o.number for o in outs] == [1, 2, 3, 4]

    # get_area should attempt update and then raise
    with pytest.raises(KeyError):
        await panel.get_area(1)
    with pytest.raises(KeyError):
        await panel.get_zone(1)


@pytest.mark.asyncio
async def test_keepalive_start_stop(monkeypatch):
    panel = DMPPanel()
    panel._connection = FakeConn([StatusResponse(areas={}, zones={})])

    # Start keepalive (task created), then stop
    await panel.start_keepalive(interval=0.01)
    assert panel._keepalive_task is not None
    await asyncio.sleep(0.03)
    await panel.stop_keepalive()
    assert panel._keepalive_task is None
