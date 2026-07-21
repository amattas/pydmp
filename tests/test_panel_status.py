"""Status/zone/area/output-status update paths, plus command-sequence
and not-connected/missing-entity edge cases from the panel test cluster."""

from typing import Any

import pytest

from pydmp.const.commands import DMPCommand
from pydmp.exceptions import DMPConnectionError
from pydmp.panel import DMPPanel
from pydmp.protocol import (
    AreaStatus,
    OutputsResponse,
    OutputStatus,
    StatusResponse,
    ZoneStatus,
)

from .fakes import cast_transport


@pytest.mark.asyncio
async def test_update_status_merges_areas_and_zones_across_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    # Merge of test_panel_update_status.py::test_update_status_merges_areas_and_zones
    # and test_panel_status_outputs.py::test_update_status_merges: exercises the
    # same merge path across multiple frames, including a trailing None frame.
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = cast_transport(_Conn())

    frames = [
        StatusResponse(areas={"1": AreaStatus("1", "D", "Main")}, zones={}),
        StatusResponse(areas={}, zones={"001": ZoneStatus("001", "N", "Front Door")}),
        None,
    ]
    state = {"i": 0}

    async def fake_send(self: DMPPanel, command: str, **kwargs: Any) -> StatusResponse | None:
        del self, command, kwargs
        i = state["i"]
        state["i"] = min(i + 1, len(frames) - 1)
        return frames[i]

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.update_status()

    areas = await p.get_areas()
    zones = await p.get_zones()
    assert len(areas) == 1
    assert len(zones) == 1
    assert areas[0].name == "Main"
    assert zones[0].name == "Front Door"


@pytest.mark.parametrize(
    ("mode", "expected_state"),
    [
        ("T", "TP"),
        ("P", "PL"),
        ("O", None),  # asserted loosely below: must land in the OFF/MO/TP/PL/ON set
        ("S", "ON"),
        ("W", "MO"),
        ("A", "MO"),
        ("a", "MO"),
        ("t", "MO"),
    ],
)
@pytest.mark.asyncio
async def test_update_output_status_maps_modes(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected_state: str | None,
) -> None:
    # Merge of test_panel_more.py::test_get_output_invalid_number_and_mode_mapping_t_p
    # and test_panel_status_outputs.py::test_update_output_status_maps_modes.
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = cast_transport(_Conn())

    outs = {"001": OutputStatus(number="001", mode=mode, name="O1")}

    async def fake_send(self: DMPPanel, command: str, **kwargs: Any) -> OutputsResponse:
        del self, command, kwargs
        return OutputsResponse(outputs=outs)

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.update_output_status()
    o1 = await p.get_output(1)
    if expected_state is None:
        assert o1._state in {"OF", "MO", "TP", "PL", "ON"}
    else:
        assert o1._state == expected_state


@pytest.mark.asyncio
async def test_update_status_command_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = cast_transport(_Conn())
    calls: list[str] = []

    async def fake_send(self: DMPPanel, command: str, **kwargs: Any) -> None:
        del self, kwargs
        calls.append(command)
        return None

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.update_status()
    # initial + 10 continuations
    assert len(calls) == 11
    assert calls[0] == DMPCommand.GET_ZONE_STATUS.value
    assert all(c == DMPCommand.GET_ZONE_STATUS_CONT.value for c in calls[1:])


@pytest.mark.asyncio
async def test_update_output_status_command_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = cast_transport(_Conn())
    calls: list[str] = []

    async def fake_send(self: DMPPanel, command: str, **kwargs: Any) -> None:
        del self, kwargs
        calls.append(command)
        return None

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.update_output_status()
    assert len(calls) == 6
    assert calls[0] == DMPCommand.GET_OUTPUT_STATUS.value
    assert all(c == DMPCommand.GET_OUTPUT_STATUS_CONT.value for c in calls[1:])


@pytest.mark.asyncio
async def test_sensor_reset_sends_command(monkeypatch: pytest.MonkeyPatch) -> None:
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = cast_transport(_Conn())
    calls: list[str] = []

    async def fake_send(self: DMPPanel, command: str, **kwargs: Any) -> str:
        del self, kwargs
        calls.append(command)
        return "ACK"

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.sensor_reset()
    assert calls == [DMPCommand.SENSOR_RESET.value]


@pytest.mark.asyncio
async def test_start_keepalive_not_connected() -> None:
    p = DMPPanel()
    with pytest.raises(DMPConnectionError):
        await p.start_keepalive(0.1)


@pytest.mark.asyncio
async def test_sensor_reset_not_connected() -> None:
    p = DMPPanel()
    with pytest.raises(DMPConnectionError):
        await p.sensor_reset()


@pytest.mark.asyncio
async def test_get_area_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    p = DMPPanel()

    async def no_update() -> None:
        return None

    monkeypatch.setattr(p, "update_status", no_update)

    class _Conn:
        is_connected = True

    p._connection = cast_transport(_Conn())
    with pytest.raises(KeyError):
        await p.get_area(99)
