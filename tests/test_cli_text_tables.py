import pytest
from click.testing import CliRunner

import pydmp.cli as cli
from tests.fakes import ConfigFactory, MinimalPanel


def test_cli_get_areas_zones_text(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    class Area:
        def __init__(self, n: int, name: str, state: str, disarmed: bool) -> None:
            self.number = n
            self.name = name
            self._state = state
            self.is_disarmed = disarmed

        @property
        def state(self) -> str:
            return self._state

    class Zone:
        def __init__(
            self,
            n: int,
            name: str,
            state: str,
            normal: bool = False,
            bypass: bool = False,
            fault: bool = False,
        ) -> None:
            self.number = n
            self.name = name
            self._state = state
            self.is_normal = normal
            self.is_bypassed = bypass
            self.has_fault = fault

        @property
        def state(self) -> str:  # noqa: D401
            return self._state

    class P(MinimalPanel):
        async def update_status(self) -> None:
            return None

        async def get_areas(self) -> list[Area]:
            return [Area(1, "A1", "D", True), Area(2, "A2", "A", False)]

        async def get_zones(self) -> list[Zone]:
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


def test_cli_quiet_and_debug_flags_via_arm(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    class P(MinimalPanel):
        async def arm_areas(self, areas: list[int], **kwargs: object) -> None:
            del areas, kwargs
            return None

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg(top_level=True)
    r_quiet = CliRunner().invoke(cli.cli, ["-q", "-c", str(cfg), "arm", "1"])  # quiet
    assert r_quiet.exit_code == 0

    r_debug = CliRunner().invoke(cli.cli, ["-d", "-c", str(cfg), "arm", "1"])  # debug
    assert r_debug.exit_code == 0
