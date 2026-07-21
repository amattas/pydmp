from typing import cast

import pytest

from pydmp.area import Area
from pydmp.output import Output
from pydmp.panel_sync import DMPPanelSync
from pydmp.zone import Zone


class _FArea:
    def __init__(self, n: int) -> None:
        self.number = n
        self.name = f"Area {n}"
        self._state = "D"

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_armed(self) -> bool:
        return False

    @property
    def is_disarmed(self) -> bool:
        return True

    async def arm(
        self,
        bypass_faulted: bool = False,
        force_arm: bool = False,
        instant: bool | None = None,
    ) -> None:
        del bypass_faulted, force_arm, instant
        self._state = "arming"

    async def disarm(self) -> None:
        self._state = "disarming"

    async def get_state(self) -> str:
        return self._state


class _FZone:
    def __init__(self, n: int) -> None:
        self.number = n
        self.name = f"Z{n}"
        self._state = "N"

    async def bypass(self) -> None:
        self._state = "X"

    async def restore(self) -> None:
        self._state = "N"

    async def get_state(self) -> str:
        return self._state


class _FOutput:
    def __init__(self, n: int) -> None:
        self.number = n
        self.name = f"Out{n}"
        self._state = ""

    async def turn_on(self) -> None:
        self._state = "ON"

    async def turn_off(self) -> None:
        self._state = "OF"

    async def pulse(self) -> None:
        self._state = "PL"

    async def toggle(self) -> None:
        self._state = "TP"


class _FPanel:
    def __init__(self, port: int = 2011, timeout: float = 10.0) -> None:
        self.port = port
        self.timeout = timeout

    async def connect(self, host: str, account_number: str, remote_key: str) -> None:
        del host, account_number, remote_key

    async def disconnect(self) -> None:
        return None

    async def get_areas(self) -> list[Area]:
        return [cast(Area, _FArea(1))]

    async def get_area(self, n: int) -> Area:
        return cast(Area, _FArea(n))

    async def get_zone(self, n: int) -> Zone:
        return cast(Zone, _FZone(n))

    async def get_output(self, n: int) -> Output:
        return cast(Output, _FOutput(n))

    async def get_outputs(self) -> list[Output]:
        return [cast(Output, _FOutput(1))]


def test_panel_sync_area_wrap(monkeypatch: pytest.MonkeyPatch) -> None:
    import pydmp.panel_sync as ps

    monkeypatch.setattr(ps, "DMPPanel", _FPanel)

    sp = DMPPanelSync()
    sp.connect("h", "1", "K")
    areas = sp.get_areas()
    assert areas and areas[0].number == 1
    a = areas[0]
    a.arm_sync()
    # state now set by fake area
    assert a.get_state_sync() in {"arming", "disarming", "D"}
    a.disarm_sync()
    assert a.get_state_sync() == "disarming"
    # Zone sync wrappers
    z = sp.get_zone(5)
    z.bypass_sync()
    assert z.get_state_sync() in {"X", "N"}
    z.restore_sync()
    assert z.get_state_sync() == "N"
    sp.disconnect()


def test_panel_sync_output_ops(monkeypatch: pytest.MonkeyPatch) -> None:
    import pydmp.panel_sync as ps

    monkeypatch.setattr(ps, "DMPPanel", _FPanel)
    sp = DMPPanelSync()
    sp.connect("h", "1", "K")
    outs = sp.get_outputs()
    assert outs and outs[0].number == 1
    o = sp.get_output(1)
    o.turn_on_sync()
    o.turn_off_sync()
    o.pulse_sync()
    o.toggle_sync()
    sp.disconnect()
