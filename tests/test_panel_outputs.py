"""Output default-creation and missing area/zone KeyError paths."""

import pytest

from pydmp.panel import DMPPanel
from pydmp.protocol import StatusResponse


@pytest.mark.asyncio
async def test_get_outputs_creates_defaults_without_connection():
    p = DMPPanel()
    outs = await p.get_outputs()
    # Should create outputs 1-4 by default
    nums = [o.number for o in outs]
    assert nums[:4] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_get_output_invalid_number_raises():
    p = DMPPanel()
    with pytest.raises(KeyError):
        await p.get_output(0)
    with pytest.raises(KeyError):
        await p.get_output(1000)


@pytest.mark.asyncio
async def test_get_outputs_and_missing_area_zone():
    # Merge of test_panel_outputs_edges.py::test_get_outputs_creates_defaults_without_connection
    # (via a live-but-empty connection this time) with the missing-area/zone
    # KeyError paths from test_panel_misc.py.
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

    panel = DMPPanel()
    # Empty status response
    panel._connection = FakeConn([StatusResponse(areas={}, zones={})])
    panel._send_command = panel._connection.send_command

    # get_outputs creates 1..4
    outs = await panel.get_outputs()
    assert [o.number for o in outs] == [1, 2, 3, 4]

    # get_area should attempt update and then raise
    with pytest.raises(KeyError):
        await panel.get_area(1)
    with pytest.raises(KeyError):
        await panel.get_zone(1)
