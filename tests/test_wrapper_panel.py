"""Compatibility tests for the new-core-backed wrapper package."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pydmp.profile import UserProfile
from pydmp.user import UserCode
from pydmp.wrapper import DMPPanel, DMPPanelSync
from pydmp.wrapper.area import Area
from pydmp.wrapper.output import Output
from pydmp.wrapper.zone import Zone


class FakeManager:
    """Small stand-in for the new-core manager used by keepalive."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def execute(self, body, *, completion=None, label=None):
        self.calls.append((str(body), label))
        return SimpleNamespace(body=body, label=label)


class FakeClient:
    """Small stand-in for `CorePanelClient` used by the wrapper tests."""

    def __init__(self) -> None:
        self.manager = FakeManager()
        self.closed = False
        self.arm_calls: list[tuple[tuple[int, ...], bool, bool, bool]] = []
        self.disarm_calls: list[tuple[int, ...]] = []
        self.bypass_calls: list[int] = []
        self.unbypass_calls: list[int] = []
        self.output_calls: list[tuple[int, str]] = []

    async def close(self) -> None:
        self.closed = True

    async def query_areas(self):
        return SimpleNamespace(
            areas=[
                SimpleNamespace(number="1", state="Y", name="PERIMETER"),
                SimpleNamespace(number="2", state="N", name="INTERIOR"),
            ]
        )

    async def query_zones(self):
        return SimpleNamespace(
            zones=[
                SimpleNamespace(number="1", status="O", name="FRONT DOOR"),
                SimpleNamespace(number="2", status="N", name="BACK DOOR"),
            ]
        )

    async def query_outputs(self, **kwargs):
        assert kwargs["namespace"] == "numeric"
        assert kwargs["named_only"] is False
        return SimpleNamespace(
            records=[
                SimpleNamespace(number=1, name="OUT 1", status="S"),
                SimpleNamespace(number=2, name="OUT 2", status="O"),
            ]
        )

    async def sensor_reset(self):
        return SimpleNamespace(acknowledged=True, detail=None)

    async def query_users(self):
        flags = SimpleNamespace(active=True, authority_1=False, temporary=False)
        return SimpleNamespace(
            users=[
                SimpleNamespace(
                    number="0001",
                    code="1111",
                    pin="9999",
                    profiles=("001", None, None, None),
                    end_date="311299",
                    legacy_exp="----",
                    flags=flags,
                    start_date="010100",
                    name="USER ONE",
                )
            ]
        )

    async def query_profiles(self):
        return SimpleNamespace(
            profiles=[
                SimpleNamespace(
                    number="001",
                    areas_mask="FFFFFFFF",
                    access_areas_mask="00000000",
                    output_group="001",
                    menu_options="00000000",
                    rearm_delay="005",
                    name="PROFILE ONE",
                )
            ]
        )

    async def arm_areas(self, areas, *, bypass_faulted=False, force_arm=False, instant=False):
        normalized = tuple(int(area) for area in areas)
        self.arm_calls.append((normalized, bypass_faulted, force_arm, instant))
        return SimpleNamespace(acknowledged=True, detail=None)

    async def disarm_areas(self, areas):
        normalized = tuple(int(area) for area in areas)
        self.disarm_calls.append(normalized)
        return SimpleNamespace(acknowledged=True, detail=None)

    async def bypass_zone(self, zone):
        self.bypass_calls.append(int(zone))
        return SimpleNamespace(acknowledged=True, detail=None)

    async def unbypass_zone(self, zone):
        self.unbypass_calls.append(int(zone))
        return SimpleNamespace(acknowledged=True, detail=None)

    async def set_output(self, selector, mode):
        self.output_calls.append((int(selector), str(mode)))
        return SimpleNamespace(selector=f"{int(selector):03d}", mode=str(mode), acknowledged=True, detail=None)


async def test_wrapper_panel_maps_old_style_api(monkeypatch) -> None:
    fake_client = FakeClient()
    monkeypatch.setattr("pydmp.wrapper.panel._build_core_client", lambda endpoint, session_profile: fake_client)

    panel = DMPPanel()
    await panel.connect("192.168.1.123", "12345", "ABCDEFGH")

    assert panel.is_connected is True

    areas = await panel.get_areas()
    assert [area.number for area in areas] == [1, 2]
    assert areas[0].state == "A"
    assert areas[0].is_armed is True
    assert areas[1].state == "D"
    assert areas[1].is_disarmed is True

    zones = await panel.get_zones()
    assert [zone.number for zone in zones] == [1, 2]
    assert zones[0].is_open is True
    assert zones[1].is_normal is True

    outputs_before = await panel.get_outputs()
    assert [output.number for output in outputs_before[:4]] == [1, 2, 3, 4]

    await panel.update_output_status()
    output_1 = await panel.get_output(1)
    output_2 = await panel.get_output(2)
    assert output_1.state == "ON"
    assert output_1.is_on is True
    assert output_2.state == "OF"
    assert output_2.is_off is True

    users = await panel.get_user_codes()
    assert len(users) == 1
    assert isinstance(users[0], UserCode)
    assert users[0].flags == "YNN"
    assert await panel.check_code("1111") is users[0]
    assert await panel.check_code("9999", include_pin=True) is users[0]

    profiles = await panel.get_user_profiles()
    assert len(profiles) == 1
    assert isinstance(profiles[0], UserProfile)
    assert profiles[0].name == "PROFILE ONE"

    await areas[0].arm(bypass_faulted=True, force_arm=True)
    await areas[1].disarm()
    await zones[0].bypass()
    await zones[0].restore()
    await output_1.turn_on()
    await output_1.turn_off()

    assert fake_client.arm_calls == [((1,), True, True, False)]
    assert fake_client.disarm_calls == [(2,)]
    assert fake_client.bypass_calls == [1]
    assert fake_client.unbypass_calls == [1]
    assert fake_client.output_calls == [(1, "S"), (1, "O")]

    await panel.disconnect()
    assert panel.is_connected is False
    assert fake_client.closed is True


def test_wrapper_panel_sync_uses_same_surface(monkeypatch) -> None:
    monkeypatch.setattr("pydmp.wrapper.panel._build_core_client", lambda endpoint, session_profile: FakeClient())

    panel = DMPPanelSync()
    panel.connect("192.168.1.123", "12345", "ABCDEFGH")

    areas = panel.get_areas()
    zones = panel.get_zones()
    outputs = panel.get_outputs()

    assert areas[0].number == 1
    assert zones[0].number == 1
    assert outputs[0].number == 1
    assert panel.is_connected is True

    panel.disconnect()
    assert panel.is_connected is False


async def test_wrapper_connect_treats_space_filled_key_as_blank_v2(monkeypatch) -> None:
    captured = {}

    def fake_build(endpoint, session_profile):
        captured["remote_key"] = endpoint.remote_key
        captured["session_profile_name"] = type(session_profile).__name__
        return FakeClient()

    monkeypatch.setattr("pydmp.wrapper.panel._build_core_client", fake_build)

    panel = DMPPanel()
    await panel.connect("192.168.1.123", "12345", "                ")

    assert captured["remote_key"] is None
    assert captured["session_profile_name"] == "SessionProfileBlankV2"

    await panel.disconnect()


async def test_wrapper_panel_keeps_old_send_command_sequences(monkeypatch) -> None:
    panel = DMPPanel()

    class _Conn:
        is_connected = True

    panel._connection = _Conn()  # type: ignore[attr-defined]
    calls: list[str] = []

    async def fake_send(self, command: str, **kwargs):
        calls.append(command)
        return None

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)

    await panel.update_status()
    assert len(calls) == 11

    calls.clear()
    await panel.update_output_status()
    assert len(calls) == 6


async def test_wrapper_entities_keep_old_command_seams() -> None:
    class FakePanel:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        async def _send_command(self, command: str, **kwargs):
            self.calls.append((command, dict(kwargs)))
            return "ACK"

        async def update_status(self):
            return None

    panel = FakePanel()

    area = Area(panel, 1, "Main", "D")
    await area.arm(bypass_faulted=True, force_arm=False, instant=None)
    await area.disarm()

    zone = Zone(panel, 5, "Front", "N")
    await zone.bypass()
    await zone.restore()

    output = Output(panel, 2, "Relay")
    await output.turn_on()
    await output.turn_off()
    await output.pulse()

    assert panel.calls[0][1]["area"] == "01"
    assert panel.calls[0][1]["bypass"] == "Y"
    assert panel.calls[0][1]["instant"] == ""
    assert panel.calls[2][1]["zone"] == "005"
    assert panel.calls[4][1]["output"] == "002"
    assert output.state == "PL"


async def test_wrapper_keepalive_uses_injected_protocol_and_transport() -> None:
    panel = DMPPanel()

    class DummyProtocol:
        def encode_command(self, command: str, **kwargs) -> bytes:
            return b"KA"

    class DummyTransport:
        def __init__(self) -> None:
            self.is_connected = True
            self.sent: list[bytes] = []

        async def send_and_receive(self, data: bytes) -> bytes:
            self.sent.append(bytes(data))
            return b""

    panel._protocol = DummyProtocol()  # type: ignore[attr-defined]
    panel._connection = DummyTransport()  # type: ignore[attr-defined]

    await panel.start_keepalive(interval=0.01)
    await asyncio.sleep(0.03)
    await panel.stop_keepalive()

    assert panel._connection.sent
