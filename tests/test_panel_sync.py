from typing import Any

from pydmp.panel_sync import DMPPanelSync


class _FArea:
    def __init__(self, n: int) -> None:
        self.number = n
        self.name = f"Area {n}"
        self._state = "D"

    @property
    def state(self) -> Any:
        return self._state

    @property
    def is_armed(self) -> Any:
        return False

    @property
    def is_disarmed(self) -> Any:
        return True

    async def arm(self, bypass_faulted: bool = False, force_arm: bool = False, instant: Any = None) -> None:
        self._state = "arming"

    async def disarm(self) -> None:
        self._state = "disarming"

    async def get_state(self) -> Any:
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

    async def get_state(self) -> Any:
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
    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def connect(self, *a: Any, **k: Any) -> Any:
        return None

    async def disconnect(self) -> Any:
        return None

    async def get_areas(self) -> Any:
        return [_FArea(1)]

    async def get_area(self, n: int) -> Any:
        return _FArea(n)

    async def get_zone(self, n: int) -> Any:
        return _FZone(n)

    async def get_output(self, n: int) -> Any:
        return _FOutput(n)

    async def get_outputs(self) -> Any:
        return [_FOutput(1)]


def test_panel_sync_area_wrap(monkeypatch: Any) -> None:
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


def test_panel_sync_output_ops(monkeypatch: Any) -> None:
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
