"""Arm/disarm logic: area validation, flag mapping, NAK handling, concatenation."""

import pytest

from pydmp.const.commands import DMPCommand
from pydmp.exceptions import DMPConnectionError
from pydmp.panel import DMPPanel
from tests.fakes import cast_transport


def _connected_panel() -> DMPPanel:
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = cast_transport(_Conn())
    return p


@pytest.mark.parametrize("method", ["arm_areas", "disarm_areas"])
@pytest.mark.parametrize(
    ("areas", "should_raise"),
    [
        ([0], True),
        ([9], True),
        ([99], True),
        ([100], True),
        ([1, 0], True),
        ([1, 9], True),
        ([], True),  # empty list -> ValueError("area_numbers must not be empty"), per panel.py
        ([1], False),
        ([8], False),
        ([1, 8], False),
    ],
)
@pytest.mark.asyncio
async def test_arm_disarm_area_validation(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    areas: list[int],
    should_raise: bool,
) -> None:
    # Area must be 1-8 to match Area's own validation (PYDMP-022); an empty
    # list is rejected before range-checking (see DMPPanel.arm_areas/disarm_areas).
    p = _connected_panel()

    async def fake_send(self: DMPPanel, command: str, **kwargs: object) -> str:
        del self, command, kwargs
        return "ACK"

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)

    if should_raise:
        with pytest.raises(ValueError):
            await getattr(p, method)(areas)
    else:
        await getattr(p, method)(areas)  # should not raise


@pytest.mark.asyncio
async def test_arm_areas_flag_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    p = _connected_panel()
    recorded: list[tuple[str, dict[str, object]]] = []

    async def fake_send(self: DMPPanel, command: str, **kwargs: object) -> str:
        del self
        recorded.append((command, dict(kwargs)))
        return "ACK"

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)

    # instant True
    await p.arm_areas([1], bypass_faulted=True, force_arm=False, instant=True)
    # instant False
    await p.arm_areas([2], bypass_faulted=False, force_arm=True, instant=False)
    # instant None
    await p.arm_areas([3], bypass_faulted=False, force_arm=False, instant=None)

    assert recorded[0][0] == DMPCommand.ARM.value
    assert recorded[0][1]["instant"] == "Y" and recorded[0][1]["bypass"] == "Y" and recorded[0][1]["force"] == "N"
    assert recorded[1][1]["instant"] == "N" and recorded[1][1]["bypass"] == "N" and recorded[1][1]["force"] == "Y"
    assert recorded[2][1]["instant"] == "" and recorded[2][1]["bypass"] == "N" and recorded[2][1]["force"] == "N"


@pytest.mark.asyncio
async def test_arm_areas_nak_and_concatenation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Merge of test_panel_arming_flags.py::test_disarm_nak and
    # test_panel_commands.py::test_arm_areas_builds_and_handles_nak: NAK
    # handling on both arm and disarm, plus the two-digit area concatenation
    # and flag-passthrough assertions.
    sent: dict[str, object] = {}

    async def fake_send(self: DMPPanel, command: str, **kwargs: object) -> str:
        del self
        sent["cmd"] = command
        sent.update(kwargs)
        return "NAK"

    p = _connected_panel()
    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)

    with pytest.raises(DMPConnectionError):
        await p.arm_areas([1, 2], bypass_faulted=True, force_arm=False, instant=True)

    assert sent["cmd"] == DMPCommand.ARM.value
    # areas_concat should be two-digit each
    assert sent["area"] == "0102"
    assert sent["bypass"] == "Y" and sent["force"] == "N" and sent["instant"] == "Y"

    async def nak_send(self: DMPPanel, command: str, **kwargs: object) -> str:
        del self, command, kwargs
        return "NAK"

    monkeypatch.setattr(DMPPanel, "_send_command", nak_send)
    with pytest.raises(DMPConnectionError):
        await p.disarm_areas([1, 2])

    # Successful disarm path
    async def ok_send(self: DMPPanel, command: str, **kwargs: object) -> str:
        del self, command, kwargs
        return "ACK"

    monkeypatch.setattr(DMPPanel, "_send_command", ok_send)
    await p.disarm_areas([3, 4])


@pytest.mark.asyncio
async def test_arm_disarm_areas_multi_and_nak_via_connection_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # test_panel_update_status.py::test_arm_disarm_areas_multi_and_nak: exercises
    # the same arm-ok/disarm-NAK behavior through send_command routing on the
    # connection object itself (rather than patching _send_command directly).
    from pydmp.protocol import AreaStatus, StatusResponse, ZoneStatus

    class FakeConnection:
        def __init__(self) -> None:
            self.is_connected = True
            self._toggle = False
            self.host = "h"
            self.port = 0
            self.account = "a"

        async def send_command(self, cmd: str, **kwargs: object) -> str | StatusResponse:
            del kwargs
            if cmd == DMPCommand.ARM.value and not self._toggle:
                self._toggle = True
                return "ACK"
            if cmd == DMPCommand.DISARM.value:
                return "NAK"
            if cmd in (DMPCommand.GET_ZONE_STATUS.value, DMPCommand.GET_ZONE_STATUS_CONT.value):
                return StatusResponse(
                    areas={"1": AreaStatus("1", "D", "Main")},
                    zones={"001": ZoneStatus("001", "N", "Front")},
                )
            return "ACK"

        async def keep_alive(self) -> None:
            return None

    panel = DMPPanel()
    connection = FakeConnection()
    panel._connection = cast_transport(connection)
    monkeypatch.setattr(panel, "_send_command", connection.send_command)

    await panel.arm_areas([1, 2], bypass_faulted=True, force_arm=False, instant=True)

    with pytest.raises(DMPConnectionError):
        await panel.disarm_areas([1, 2])
