import asyncio

import pytest

from pydmp.area import Area, AreaSync
from pydmp.const.events import DMPRealTimeStatusEvent
from pydmp.exceptions import (
    DMPAreaError,
    DMPInvalidParameterError,
    DMPOutputError,
    DMPZoneError,
)
from pydmp.output import Output, OutputSync
from pydmp.panel import DMPPanel
from pydmp.status_parser import parse_s3_message
from pydmp.status_server import S3Message
from pydmp.zone import Zone, ZoneSync


class FakeConnection:
    """Fake panel connection used by the integration-style tests."""

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


class _FakePanel:
    """Fake panel exposing the minimal surface used by Area/Zone/Output."""

    def __init__(self, reply="ACK"):
        self.reply = reply
        self.updated = False

    async def _send_command(self, *a, **k):
        return self.reply

    async def update_status(self):
        self.updated = True


class _SyncPanel:
    """Fake sync panel that drives coroutines via the default event loop."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Constructor validation / state update / get_state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_cls,valid_number,invalid_number",
    [
        (Area, 1, 0),
        (Zone, 5, 0),
        (Output, 12, 0),
    ],
)
async def test_entity_constructor_validation_and_state_updates(
    entity_cls, valid_number, invalid_number
):
    p = _FakePanel()
    with pytest.raises(DMPInvalidParameterError):
        entity_cls(p, invalid_number)

    e = entity_cls(p, valid_number, name="Orig", state="D")
    e.update_state("X", name="Updated")
    assert e.name == "Updated" and e.state == "X"

    if entity_cls is Output:
        # Output has no get_state()/update_status hook; verify its own extra instead.
        assert e.formatted_number == "012"
        return

    # Area and Zone expose get_state(), which triggers panel.update_status().
    p2 = _FakePanel()
    e2 = entity_cls(p2, valid_number, name="Orig2")
    await e2.get_state()
    assert p2.updated is True


# ---------------------------------------------------------------------------
# Sync-wrapper accessor/repr trio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entity_cls,sync_cls,class_name",
    [
        (Area, AreaSync, "AreaSync"),
        (Zone, ZoneSync, "ZoneSync"),
        (Output, OutputSync, "OutputSync"),
    ],
)
def test_entity_sync_accessors_and_repr(entity_cls, sync_cls, class_name):
    p = _FakePanel()
    e = entity_cls(p, 2, name="Two", state="D")
    s = sync_cls(e, _SyncPanel())
    assert s.number == 2 and s.name == "Two" and s.state == "D"
    assert isinstance(repr(s), str) and class_name in repr(s)


# ---------------------------------------------------------------------------
# Area-specific behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_area_arm_disarm_error_paths():
    p = _FakePanel(reply="NAK")
    a = Area(p, 1, name="A1", state="D")

    with pytest.raises(DMPAreaError):
        await a.arm(bypass_faulted=True, force_arm=False, instant=True)

    with pytest.raises(DMPAreaError):
        await a.disarm()


# ---------------------------------------------------------------------------
# Zone-specific behavior: bypass/restore success + NAK cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,reply,expect_error",
    [
        ("bypass", "ACK", False),
        ("restore", "ACK", False),
        ("bypass", "NAK", True),
        ("restore", "NAK", True),
    ],
)
async def test_zone_bypass_restore(action, reply, expect_error):
    z = Zone(_FakePanel(reply=reply), 1, name="Front", state="N")
    method = getattr(z, action)
    if expect_error:
        with pytest.raises(DMPZoneError):
            await method()
    else:
        await method()


# ---------------------------------------------------------------------------
# Output-specific behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_output_set_modes_and_toggle():
    p = _FakePanel()
    o = Output(p, 1, "R1")
    await o.turn_on()
    assert o.is_on
    await o.toggle()
    # previous was ON so toggle calls turn_off
    assert o.is_off


@pytest.mark.asyncio
async def test_output_nak_error():
    p = _FakePanel(reply="NAK")
    o = Output(p, 1, "R1")
    with pytest.raises(DMPOutputError):
        await o.pulse()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,expected_state",
    [
        ("M", DMPRealTimeStatusEvent.OUTPUT_ON.value),
        ("O", DMPRealTimeStatusEvent.OUTPUT_OFF.value),
        ("P", DMPRealTimeStatusEvent.OUTPUT_PULSE.value),
        ("S", DMPRealTimeStatusEvent.OUTPUT_ON.value),
    ],
)
async def test_output_set_mode_mapping(mode, expected_state):
    o = Output(_FakePanel(), 1, "R1")
    await o.set_mode(mode)
    assert o.state == expected_state


# ---------------------------------------------------------------------------
# Integration-style tests (moved as-is)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_area_basic_states_and_commands():
    panel = DMPPanel()
    panel._connection = FakeConnection()
    panel._send_command = panel._connection.send_command
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
    panel._send_command = panel._connection.send_command

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
    panel._send_command = panel._connection.send_command

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


# ---------------------------------------------------------------------------
# repr / misc (moved as-is)
# ---------------------------------------------------------------------------


def test_entity_reprs():
    panel = DMPPanel()
    # Panel repr before connect
    r = repr(panel)
    assert "disconnected" in r

    a = Area(panel, 1, "Main", state="D")
    z = Zone(panel, 2, "Front", state="N")
    o = Output(panel, 3, "Relay")

    assert "Area" in repr(a)
    assert "Zone" in repr(z)
    assert "Output" in repr(o)


def test_status_parser_unknown_category():
    msg = S3Message(account="00001", definition="Z?", type_code=None, fields=["Z?"], raw="")
    evt = parse_s3_message(msg)
    assert evt.category is None
    assert evt.code_enum is None
