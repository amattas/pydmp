from pydmp.panel_sync import DMPPanelSync


class _FArea:
    def __init__(self, n: int):
        self.number = n
        self.name = f"Area {n}"
        self._state = "D"

    @property
    def state(self):
        return self._state

    @property
    def is_armed(self):
        return False

    @property
    def is_disarmed(self):
        return True

    async def arm(self, bypass_faulted: bool = False, force_arm: bool = False, instant=None):
        self._state = "arming"

    async def disarm(self):
        self._state = "disarming"

    async def get_state(self):
        return self._state


class _FPanel:
    def __init__(self, *a, **k):
        pass

    async def connect(self, *a, **k):
        return None

    async def disconnect(self):
        return None

    async def get_areas(self):
        return [_FArea(1)]

    async def get_area(self, n: int):
        return _FArea(n)

    async def get_zone(self, n: int):
        class Z:
            def __init__(self, num):
                self.number = num
                self.name = f"Z{num}"
                self._state = "N"

            async def bypass(self):
                self._state = "X"

            async def restore(self):
                self._state = "N"

            async def get_state(self):
                return self._state

        return Z(n)


def test_panel_sync_area_wrap(monkeypatch):
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
