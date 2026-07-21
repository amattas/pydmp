import asyncio
from collections.abc import Coroutine
from typing import TypeVar, cast

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
from pydmp.panel_sync import DMPPanelSync
from pydmp.status_parser import parse_s3_message
from pydmp.status_server import S3Message
from pydmp.zone import Zone, ZoneSync
from tests.fakes import PanelResponse, cast_panel, cast_transport

T = TypeVar("T")
EntityClass = type[Area] | type[Zone] | type[Output]
SyncEntityClass = type[AreaSync] | type[ZoneSync] | type[OutputSync]


class FakeConnection:
    """Fake panel connection used by the integration-style tests."""

    def __init__(self, response_map: dict[str, PanelResponse] | None = None) -> None:
        self.is_connected = True
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.response_map = response_map or {}
        self.host = "h"
        self.port = 0
        self.account = "a"

    async def send_command(self, cmd: str, **kwargs: object) -> PanelResponse:
        self.calls.append((cmd, kwargs))
        return self.response_map.get(cmd, "ACK")

    async def keep_alive(self) -> None:
        self.calls.append(("!H", {}))


class _FakePanel:
    """Fake panel exposing the minimal surface used by Area/Zone/Output."""

    def __init__(self, reply: str = "ACK") -> None:
        self.reply = reply
        self.updated = False

    async def _send_command(self, command: str, **kwargs: object) -> str:
        del command, kwargs
        return self.reply

    async def update_status(self) -> None:
        self.updated = True


class _SyncPanel:
    """Fake sync panel that drives coroutines via the default event loop."""

    def _run(self, coro: Coroutine[object, object, T]) -> T:
        return asyncio.run(coro)


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
    entity_cls: EntityClass,
    valid_number: int,
    invalid_number: int,
) -> None:
    p = cast_panel(_FakePanel())
    with pytest.raises(DMPInvalidParameterError):
        entity_cls(p, invalid_number)

    e = entity_cls(p, valid_number, name="Orig", state="D")
    e.update_state("X", name="Updated")
    assert e.name == "Updated" and e.state == "X"

    if entity_cls is Output:
        # Output has no get_state()/update_status hook; verify its own extra instead.
        assert cast(Output, e).formatted_number == "012"
        return

    # Area and Zone expose get_state(), which triggers panel.update_status().
    raw_panel = _FakePanel()
    p2 = cast_panel(raw_panel)
    e2 = entity_cls(p2, valid_number, name="Orig2")
    await cast(Area | Zone, e2).get_state()
    assert raw_panel.updated is True


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
def test_entity_sync_accessors_and_repr(
    entity_cls: EntityClass,
    sync_cls: SyncEntityClass,
    class_name: str,
) -> None:
    p = cast_panel(_FakePanel())
    e = entity_cls(p, 2, name="Two", state="D")
    sync_panel = cast(DMPPanelSync, _SyncPanel())
    if sync_cls is AreaSync:
        s: AreaSync | ZoneSync | OutputSync = AreaSync(cast(Area, e), sync_panel)
    elif sync_cls is ZoneSync:
        s = ZoneSync(cast(Zone, e), sync_panel)
    else:
        s = OutputSync(cast(Output, e), sync_panel)
    assert s.number == 2 and s.name == "Two" and s.state == "D"
    assert isinstance(repr(s), str) and class_name in repr(s)


# ---------------------------------------------------------------------------
# Area-specific behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_area_arm_disarm_error_paths() -> None:
    p = cast_panel(_FakePanel(reply="NAK"))
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
async def test_zone_bypass_restore(action: str, reply: str, expect_error: bool) -> None:
    z = Zone(cast_panel(_FakePanel(reply=reply)), 1, name="Front", state="N")
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
async def test_output_set_modes_and_toggle() -> None:
    p = cast_panel(_FakePanel())
    o = Output(p, 1, "R1")
    await o.turn_on()
    assert o.is_on
    await o.toggle()
    # previous was ON so toggle calls turn_off
    assert o.is_off


@pytest.mark.asyncio
async def test_output_nak_error() -> None:
    p = cast_panel(_FakePanel(reply="NAK"))
    o = Output(p, 1, "R1")
    with pytest.raises(DMPOutputError):
        await o.pulse()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,expected_state",
    [
        ("M", DMPRealTimeStatusEvent.OUTPUT_MOMENTARY.value),
        ("O", DMPRealTimeStatusEvent.OUTPUT_OFF.value),
        ("P", DMPRealTimeStatusEvent.OUTPUT_PULSE.value),
        ("S", DMPRealTimeStatusEvent.OUTPUT_ON.value),
    ],
)
async def test_output_set_mode_mapping(mode: str, expected_state: str) -> None:
    o = Output(cast_panel(_FakePanel()), 1, "R1")
    await o.set_mode(mode)
    assert o.state == expected_state


# ---------------------------------------------------------------------------
# Integration-style tests (moved as-is)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_area_basic_states_and_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    panel = DMPPanel()
    connection = FakeConnection()
    panel._connection = cast_transport(connection)
    monkeypatch.setattr(panel, "_send_command", connection.send_command)
    # Fake connected flag
    assert connection.is_connected

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
async def test_zone_bypass_restore_and_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    panel = DMPPanel()
    connection = FakeConnection()
    panel._connection = cast_transport(connection)
    monkeypatch.setattr(panel, "_send_command", connection.send_command)

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
async def test_output_modes_and_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    panel = DMPPanel()
    connection = FakeConnection()
    panel._connection = cast_transport(connection)
    monkeypatch.setattr(panel, "_send_command", connection.send_command)

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


def test_entity_reprs() -> None:
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


def test_status_parser_unknown_category() -> None:
    msg = S3Message(account="00001", definition="Z?", type_code=None, fields=["Z?"], raw="")
    evt = parse_s3_message(msg)
    assert evt.category is None
    assert evt.code_enum is None
