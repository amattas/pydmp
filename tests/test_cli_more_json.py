import json
from pathlib import Path

from click.testing import CliRunner

import pydmp.cli as cli


def _cfg(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "panel:\n  host: h\n  account: '1'\n  remote_key: 'K'\n  port: 2011\n  timeout: 1\n"
    )
    return p


def test_cli_arm_json(monkeypatch, tmp_path):
    recorded = {}

    class P:
        def __init__(self, *a, **k):
            pass

        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def arm_areas(self, areas, bypass_faulted=False, force_arm=False, instant=None):
            recorded["areas"] = list(areas)
            recorded["bypass"] = bypass_faulted
            recorded["force"] = force_arm
            recorded["instant"] = instant

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = _cfg(tmp_path)
    r = CliRunner().invoke(
        cli.cli,
        ["-c", str(cfg), "arm", "1,2", "--bypass-faulted", "--no-instant", "--json"],
    )
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert payload["ok"] and payload["areas"] == [1, 2]
    assert recorded == {"areas": [1, 2], "bypass": True, "force": False, "instant": False}


def test_cli_get_outputs_json(monkeypatch, tmp_path):
    class OutputStub:
        def __init__(self, n):
            self.number = n
            self.name = f"Out{n}"
            self._state = "ON"

        def to_dict(self):
            return {"number": self.number, "name": self.name, "state": self._state}

    class P:
        def __init__(self, *a, **k):
            pass

        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def update_output_status(self):
            return None

        async def get_outputs(self):
            return [OutputStub(1), OutputStub(2)]

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = _cfg(tmp_path)
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "get-outputs", "--json"])
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["ok"] and len(data["outputs"]) == 2


def test_cli_disarm_error_json(monkeypatch, tmp_path):
    class P:
        def __init__(self, *a, **k):
            pass

        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def disarm_areas(self, areas):
            raise Exception("cannot disarm")

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = _cfg(tmp_path)
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "disarm", "1", "--json"])
    assert r.exit_code != 0
    # Ensure the error reason is surfaced
    assert "cannot disarm" in r.output
