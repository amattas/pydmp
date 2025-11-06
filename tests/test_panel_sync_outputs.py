from pydmp.panel_sync import DMPPanelSync


class _FOutput:
    def __init__(self, n: int):
        self.number = n
        self.name = f"Out{n}"
        self._state = ""

    async def turn_on(self):
        self._state = "ON"

    async def turn_off(self):
        self._state = "OF"

    async def pulse(self):
        self._state = "PL"

    async def toggle(self):
        self._state = "TP"


class _FPanel:
    def __init__(self, *a, **k):
        pass

    async def connect(self, *a, **k):
        return None

    async def disconnect(self):
        return None

    async def get_output(self, n: int):
        return _FOutput(n)

    async def get_outputs(self):
        return [_FOutput(1)]


def test_panel_sync_output_ops(monkeypatch):
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
