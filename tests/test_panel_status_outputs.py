import pytest

from pydmp.panel import DMPPanel
from pydmp.protocol import AreaStatus, OutputsResponse, OutputStatus, StatusResponse, ZoneStatus


@pytest.mark.asyncio
async def test_update_status_merges(monkeypatch):
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]

    frames = [
        StatusResponse(areas={"1": AreaStatus("1", "D", "Main")}, zones={}),
        StatusResponse(areas={}, zones={"001": ZoneStatus("001", "N", "Front")}),
        None,
    ]
    state = {"i": 0}

    async def fake_send(self, command: str, **kwargs):
        i = state["i"]
        state["i"] = min(i + 1, len(frames) - 1)
        return frames[i]

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.update_status()
    areas = await p.get_areas()
    zones = await p.get_zones()
    assert areas and areas[0].name == "Main"
    assert zones and zones[0].name == "Front"


@pytest.mark.asyncio
async def test_update_output_status_maps_modes(monkeypatch):
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]

    outs = {
        "001": OutputStatus(number="001", mode="O", name="Relay1"),
        "002": OutputStatus(number="002", mode="S", name="Relay2"),
        "003": OutputStatus(number="003", mode="W", name="Relay3"),
        "004": OutputStatus(number="004", mode="A", name="Relay4"),
        "005": OutputStatus(number="005", mode="a", name="Relay5"),
        "006": OutputStatus(number="006", mode="t", name="Relay6"),
    }

    async def fake_send(self, command: str, **kwargs):
        return OutputsResponse(outputs=outs)

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.update_output_status()
    o1 = await p.get_output(1)
    o2 = await p.get_output(2)
    o3 = await p.get_output(3)
    o4 = await p.get_output(4)
    o5 = await p.get_output(5)
    o6 = await p.get_output(6)
    # internal state mapping check (OFF and ON codes)
    assert o1._state in {"OF", "MO", "TP", "PL", "ON"}
    assert o2._state == "ON"
    # modes W/A/a/t map to MO
    assert o3._state == "MO" and o4._state == "MO" and o5._state == "MO" and o6._state == "MO"
