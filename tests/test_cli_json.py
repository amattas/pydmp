import json
from pathlib import Path

from click.testing import CliRunner

import pydmp.cli as cli
from pydmp.protocol import UserCode


def _write_cfg(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "panel:\n  host: h\n  account: '1'\n  remote_key: 'K'\n  port: 2011\n  timeout: 1\n"
    )
    return p


class _FakePanel:
    def __init__(self, *a, **k):
        pass

    async def connect(self, *a, **k):
        return None

    async def disconnect(self):
        return None

    async def update_status(self):
        return None

    async def get_areas(self):
        class A:
            def __init__(self, n):
                self.number = n

            def to_dict(self):
                return {"number": self.number, "name": f"Area {self.number}", "state": "D"}

        return [A(1), A(2)]

    async def get_user_codes(self):
        u = UserCode(
            number="0001",
            code="1234",
            pin="",
            profiles=("001", "002", "003", "004"),
            temp_date="010125",
            exp_date="0900",
            name="USER",
        )
        return [u]

    async def get_user_profiles(self):
        from pydmp.protocol import UserProfile

        p = UserProfile(
            number="001",
            areas_mask="C3000000",
            access_areas_mask="C3000000",
            output_group="001",
            menu_options="MENUOPTS",
            rearm_delay="005",
            name="ADMIN",
        )
        return [p]


def test_cli_get_areas_json(monkeypatch, tmp_path):
    cfg = _write_cfg(tmp_path)
    monkeypatch.setattr(cli, "DMPPanel", _FakePanel)
    runner = CliRunner()
    res = runner.invoke(cli.cli, ["--config", str(cfg), "get-areas", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["ok"] and len(data["areas"]) == 2


def test_cli_get_users_profiles_json(monkeypatch, tmp_path):
    cfg = _write_cfg(tmp_path)
    monkeypatch.setattr(cli, "DMPPanel", _FakePanel)
    runner = CliRunner()
    res = runner.invoke(cli.cli, ["--config", str(cfg), "get-users", "--json"])
    assert res.exit_code == 0
    users = json.loads(res.output)["users"]
    assert users and users[0]["number"] == "0001"

    res2 = runner.invoke(cli.cli, ["--config", str(cfg), "get-profiles", "--json"])
    assert res2.exit_code == 0
    profiles = json.loads(res2.output)["profiles"]
    assert profiles and profiles[0]["number"] == "001"
