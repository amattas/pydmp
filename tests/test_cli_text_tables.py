from click.testing import CliRunner

import pydmp.cli as cli


def test_cli_get_areas_zones_text(monkeypatch, cli_cfg):
    class Area:
        def __init__(self, n, name, state, disarmed):
            self.number = n
            self.name = name
            self._state = state
            self.is_disarmed = disarmed

        @property
        def state(self):
            return self._state

    class Zone:
        def __init__(self, n, name, state, normal=False, bypass=False, fault=False):
            self.number = n
            self.name = name
            self._state = state
            self.is_normal = normal
            self.is_bypassed = bypass
            self.has_fault = fault

        @property
        def state(self):  # noqa: D401
            return self._state

    class P:
        def __init__(self, *a, **k):
            pass

        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def update_status(self):
            return None

        async def get_areas(self):
            return [Area(1, "A1", "D", True), Area(2, "A2", "A", False)]

        async def get_zones(self):
            return [
                Zone(1, "Z1", "N", normal=True),
                Zone(2, "Z2", "O", normal=False, fault=True),
            ]

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r1 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "get-areas"])  # text
    assert r1.exit_code == 0 and "Areas" in r1.output

    r2 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "get-zones"])  # text
    assert r2.exit_code == 0 and "Zones" in r2.output


def test_cli_quiet_and_debug_flags_via_arm(monkeypatch, cli_cfg):
    class P:
        def __init__(self, *a, **k):
            pass

        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def arm_areas(self, *a, **k):
            return None

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg(top_level=True)
    r_quiet = CliRunner().invoke(cli.cli, ["-q", "-c", str(cfg), "arm", "1"])  # quiet
    assert r_quiet.exit_code == 0

    r_debug = CliRunner().invoke(cli.cli, ["-d", "-c", str(cfg), "arm", "1"])  # debug
    assert r_debug.exit_code == 0
