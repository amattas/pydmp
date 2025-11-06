import pytest

from pydmp.area import Area
from pydmp.const.events import DMPRealTimeStatusEvent
from pydmp.output import Output
from pydmp.panel import DMPPanel
from pydmp.zone import Zone


class FakeConnection:
    def __init__(self, response_map=None):
        self.is_connected = True
        self.calls = []
        self.response_map = response_map or {}
        self.host = "h"
        self.port = 0
        self.account = "a"

    async def send_command(self, cmd: str, **kwargs):
        self.calls.append((cmd, kwargs))
        return self.response_map.get(cmd, "ACK")

    async def keep_alive(self):
        self.calls.append(("!H", {}))


@pytest.mark.asyncio
async def test_area_basic_states_and_commands():
    panel = DMPPanel()
    panel._connection = FakeConnection()
    # Fake connected flag
    assert panel._connection.is_connected

    a = Area(panel, 1, name="Main", state="D")
    assert a.is_disarmed
    assert not a.is_armed

    await a.arm(bypass_faulted=False, force_arm=False, instant=None)
    assert a.state == "arming"

    await a.arm(bypass_faulted=True, force_arm=False, instant=True)
    # Still "arming" locally; protocol confirmation comes via status
    assert a.state == "arming"

    await a.disarm()
    assert a.state == "disarming"


@pytest.mark.asyncio
async def test_zone_bypass_restore_and_helpers():
    panel = DMPPanel()
    panel._connection = FakeConnection()

    z = Zone(panel, 5, name="Front", state="N")
    assert z.is_normal
    assert not z.is_open
    assert not z.is_bypassed
    assert z.formatted_number == "005"

    await z.bypass()
    z.update_state("X")
    assert z.is_bypassed
    assert z.has_fault is False

    z.update_state("S")
    assert z.has_fault is True

    await z.restore()


@pytest.mark.asyncio
async def test_output_modes_and_toggle():
    panel = DMPPanel()
    panel._connection = FakeConnection()

    o = Output(panel, 2, name="Relay")
    await o.turn_on()
    assert o.state == DMPRealTimeStatusEvent.OUTPUT_ON.value
    assert o.is_on
    assert not o.is_off

    await o.turn_off()
    assert o.state == DMPRealTimeStatusEvent.OUTPUT_OFF.value
    assert o.is_off

    await o.pulse()
    assert o.state == DMPRealTimeStatusEvent.OUTPUT_PULSE.value

    # Toggle from pulse should turn on
    await o.toggle()
    assert o.is_on
