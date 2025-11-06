import asyncio
import pytest

from pydmp.panel import DMPPanel
from pydmp.protocol import StatusResponse, AreaStatus, ZoneStatus
from pydmp.const.commands import DMPCommand
from pydmp.exceptions import DMPConnectionError


class FakeConnection:
    def __init__(self, responses):
        self.is_connected = True
        self._responses = list(responses)
        self.calls = []
        self.host = "h"; self.port = 0; self.account = "a"

    async def send_command(self, cmd: str, **kwargs):
        self.calls.append((cmd, kwargs))
        # Return the next StatusResponse for WB queries; else ACK
        if cmd in (DMPCommand.GET_ZONE_STATUS.value, DMPCommand.GET_ZONE_STATUS_CONT.value):
            if self._responses:
                return self._responses.pop(0)
        return "ACK"

    async def keep_alive(self):
        self.calls.append(("!H", {}))


@pytest.mark.asyncio
async def test_update_status_merges_areas_and_zones():
    sr = StatusResponse(
        areas={"1": AreaStatus(number="1", state="D", name="Main")},
        zones={"001": ZoneStatus(number="001", state="N", name="Front Door")},
    )
    panel = DMPPanel()
    panel._connection = FakeConnection([sr])

    await panel.update_status()

    areas = await panel.get_areas()
    zones = await panel.get_zones()
    assert len(areas) == 1
    assert len(zones) == 1
    assert areas[0].name == "Main"
    assert zones[0].name == "Front Door"


@pytest.mark.asyncio
async def test_arm_disarm_areas_multi_and_nak():
    # First call ACK, then NAK to exercise error
    class Conn(FakeConnection):
        def __init__(self):
            super().__init__(responses=[])
            self._toggle = False

        async def send_command(self, cmd: str, **kwargs):
            if cmd == DMPCommand.ARM.value and not self._toggle:
                self._toggle = True
                return "ACK"
            if cmd == DMPCommand.DISARM.value:
                return "NAK"
            return await super().send_command(cmd, **kwargs)

    panel = DMPPanel()
    panel._connection = Conn()

    await panel.arm_areas([1, 2], bypass_faulted=True, force_arm=False, instant=True)

    with pytest.raises(DMPConnectionError):
        await panel.disarm_areas([1, 2])


@pytest.mark.asyncio
async def test_single_connection_guard(monkeypatch):
    # Simulate active connection key already present
    from pydmp import panel as panel_mod

    key = ("127.0.0.1", 2011, "00001")
    panel_mod._ACTIVE_CONNECTIONS.add(key)
    try:
        p = DMPPanel()
        # Prevent real DMPConnection.connect and update_status
        class NoopConn:
            async def connect(self):
                return None

        async def no_upd():
            return None

        # monkeypatch connection and update_status
        monkeypatch.setattr(panel_mod, "DMPConnection", lambda *a, **k: NoopConn())
        monkeypatch.setattr(DMPPanel, "update_status", lambda self: no_upd())

        with pytest.raises(DMPConnectionError):
            await p.connect("127.0.0.1", "00001", "KEY")
    finally:
        panel_mod._ACTIVE_CONNECTIONS.discard(key)

