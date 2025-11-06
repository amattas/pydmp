import json
from pathlib import Path

from click.testing import CliRunner

import pydmp.cli as cli
from pydmp.protocol import UserCode


def _cfg(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "panel:\n  host: h\n  account: '1'\n  remote_key: 'K'\n  port: 2011\n  timeout: 1\n"
    )
    return p


class _Out:
    def __init__(self, num):
        self.number = num
        self.name = f"Output {num}"
        self._state = ""

    def to_dict(self):
        return {"number": self.number, "name": self.name, "state": self._state}

    async def turn_on(self):
        self._state = "ON"

    async def turn_off(self):
        self._state = "OF"

    async def pulse(self):
        self._state = "PL"

    async def toggle(self):
        self._state = "TP"


class _Panel:
    def __init__(self, *a, **k):
        self._protocol = type("P", (), {"last_nak_detail": "XU"})()

    async def connect(self, *a, **k):
        return None

    async def disconnect(self):
        return None

    async def disarm_areas(self, areas):
        return None

    async def _send_command(self, cmd, **kwargs):
        # simulate success first, then NAK for restore to exercise both paths in separate runs
        if cmd.endswith("X") or cmd.endswith("Y"):
            return "ACK"
        return "ACK"

    async def update_output_status(self):
        return None

    async def get_outputs(self):
        o = _Out(1)
        o._state = "ON"
        return [o]

    async def get_output(self, n: int):
        return _Out(n)

    async def sensor_reset(self):
        return None

    async def check_code(self, code: str, include_pin: bool = True):
        if code == "1234":
            return UserCode(
                number="0001",
                code="1234",
                pin="",
                profiles=("001", "002", "003", "004"),
                temp_date="010125",
                exp_date="0900",
                name="USER",
            )
        return None


def test_cli_disarm_and_output_json(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "DMPPanel", _Panel)
    runner = CliRunner()

    # disarm
    res = runner.invoke(cli.cli, ["-c", str(cfg), "disarm", "1", "--json"])
    assert res.exit_code == 0

    # output set
    res2 = runner.invoke(cli.cli, ["-c", str(cfg), "output", "1", "on", "--json"])
    assert res2.exit_code == 0
    payload = json.loads(res2.output)
    assert payload["ok"] and payload["output"] == 1 and payload["mode"] == "on"


def test_cli_zone_bypass_restore_json(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    runner = CliRunner()

    class P1(_Panel):
        async def _send_command(self, cmd, **kwargs):
            return "ACK"

    monkeypatch.setattr(cli, "DMPPanel", P1)
    # bypass ok (uses P1)
    r1 = runner.invoke(cli.cli, ["-c", str(cfg), "set-zone-bypass", "5", "--json"])
    assert r1.exit_code == 0

    # restore error path should exit non-zero
    class P2(_Panel):
        async def _send_command(self, cmd, **kwargs):
            return "NAK"

    monkeypatch.setattr(cli, "DMPPanel", P2)
    r2 = runner.invoke(cli.cli, ["-c", str(cfg), "set-zone-restore", "5", "--json"])
    assert r2.exit_code != 0
    data = json.loads(r2.output)
    assert not data["ok"] and "restore zone" in data["error"]


def test_cli_zone_bypass_nak_json(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    runner = CliRunner()

    class P(_Panel):
        async def _send_command(self, cmd, **kwargs):
            return "NAK"

    monkeypatch.setattr(cli, "DMPPanel", P)
    r = runner.invoke(cli.cli, ["-c", str(cfg), "set-zone-bypass", "5", "--json"])
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert not data["ok"] and "bypass zone" in data["error"]


def test_cli_sensor_and_check_code_json(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "DMPPanel", _Panel)
    runner = CliRunner()

    # sensor reset
    r = runner.invoke(cli.cli, ["-c", str(cfg), "sensor-reset", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.output)["ok"]

    # check-code found
    r2 = runner.invoke(cli.cli, ["-c", str(cfg), "check-code", "1234", "--json"])
    assert r2.exit_code == 0
    d = json.loads(r2.output)
    assert d["ok"] and d["found"] and d["user"]["number"] == "0001"
    # not found
    r3 = runner.invoke(cli.cli, ["-c", str(cfg), "check-code", "9999", "--json"])
    assert r3.exit_code == 0
    d2 = json.loads(r3.output)
    assert d2["ok"] and not d2["found"] and d2["user"] is None


def test_cli_output_error_json(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)

    class P(_Panel):
        async def get_output(self, n: int):
            class OutputStub:
                async def turn_on(self):
                    from pydmp.exceptions import DMPOutputError

                    raise DMPOutputError("fail")

            return OutputStub()

    monkeypatch.setattr(cli, "DMPPanel", P)
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "output", "1", "on", "--json"])
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert not data["ok"] and "fail" in data["error"]
