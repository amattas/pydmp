import pytest

from pydmp.const.commands import DMPCommand
from pydmp.panel import DMPPanel
from pydmp.protocol import UserProfile, UserProfilesResponse


@pytest.mark.asyncio
async def test_update_status_command_sequence(monkeypatch):
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]
    calls: list[str] = []

    async def fake_send(self, command: str, **kwargs):
        calls.append(command)
        return None

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.update_status()
    # initial + 10 continuations
    assert len(calls) == 11
    assert calls[0] == DMPCommand.GET_ZONE_STATUS.value
    assert all(c == DMPCommand.GET_ZONE_STATUS_CONT.value for c in calls[1:])


@pytest.mark.asyncio
async def test_update_output_status_command_sequence(monkeypatch):
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]
    calls: list[str] = []

    async def fake_send(self, command: str, **kwargs):
        calls.append(command)
        return None

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.update_output_status()
    assert len(calls) == 6
    assert calls[0] == DMPCommand.GET_OUTPUT_STATUS.value
    assert all(c == DMPCommand.GET_OUTPUT_STATUS_CONT.value for c in calls[1:])


@pytest.mark.asyncio
async def test_sensor_reset_sends_command(monkeypatch):
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]
    calls: list[str] = []

    async def fake_send(self, command: str, **kwargs):
        calls.append(command)
        return "ACK"

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.sensor_reset()
    assert calls == [DMPCommand.SENSOR_RESET.value]


@pytest.mark.asyncio
async def test_get_user_profiles_pagination(monkeypatch):
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]

    def prof(num: str) -> UserProfile:
        return UserProfile(
            number=num,
            areas_mask="C3000000",
            access_areas_mask="C3000000",
            output_group="001",
            menu_options="MENUOPTS",
            rearm_delay="005",
            name=f"P{num}",
        )

    pages = [
        UserProfilesResponse(profiles=[prof("001")], has_more=True, last_number="001"),
        UserProfilesResponse(profiles=[prof("002")], has_more=False, last_number="002"),
    ]
    state = {"i": 0}

    async def fake_send(self, command: str, **kwargs):
        i = state["i"]
        state["i"] = min(i + 1, len(pages) - 1)
        return pages[i]

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    profiles = await p.get_user_profiles()
    assert [pr.number for pr in profiles] == ["001", "002"]
