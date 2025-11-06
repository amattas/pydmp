from pathlib import Path

from click.testing import CliRunner

import pydmp.cli as cli
from pydmp.protocol import UserCode, UserProfile


def _cfg_top(tmp_path: Path) -> Path:
    # top-level mapping (not nested under 'panel') to exercise normalization in CLI
    p = tmp_path / "cfg.yaml"
    p.write_text("host: h\naccount: '1'\nremote_key: 'K'\nport: 2011\ntimeout: 1\n")
    return p


def _cfg(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "panel:\n  host: h\n  account: '1'\n  remote_key: 'K'\n  port: 2011\n  timeout: 1\n"
    )
    return p


def test_cli_get_areas_zones_text(monkeypatch, tmp_path):
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
    cfg = _cfg(tmp_path)
    r1 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "get-areas"])  # text
    assert r1.exit_code == 0 and "Areas" in r1.output

    r2 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "get-zones"])  # text
    assert r2.exit_code == 0 and "Zones" in r2.output


def test_cli_get_users_profiles_text(monkeypatch, tmp_path):
    class P:
        def __init__(self, *a, **k):
            pass

        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def get_user_codes(self):
            return [
                UserCode(
                    number="0001",
                    code="1234",
                    pin="",
                    profiles=("001", "002", "003", "004"),
                    temp_date="010125",
                    exp_date="0900",
                    start_date="010125",
                    end_date="310125",
                    flags="YYN",
                    active=True,
                    temporary=False,
                    name="USER",
                )
            ]

        async def get_user_profiles(self):
            return [
                UserProfile(
                    number="001",
                    areas_mask="C3000000",
                    access_areas_mask="C3000000",
                    output_group="001",
                    menu_options="MENUOPTS",
                    rearm_delay="005",
                    name="ADMIN",
                )
            ]

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = _cfg(tmp_path)
    r1 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "get-users"])  # text
    assert r1.exit_code == 0 and "Users" in r1.output

    r2 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "get-profiles"])  # text
    assert r2.exit_code == 0 and "Profiles" in r2.output


def test_cli_quiet_and_debug_flags_via_arm(monkeypatch, tmp_path):
    class P:
        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def arm_areas(self, *a, **k):
            return None

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = _cfg_top(tmp_path)
    r_quiet = CliRunner().invoke(cli.cli, ["-q", "-c", str(cfg), "arm", "1"])  # quiet
    assert r_quiet.exit_code == 0

    r_debug = CliRunner().invoke(cli.cli, ["-d", "-c", str(cfg), "arm", "1"])  # debug
    assert r_debug.exit_code == 0
