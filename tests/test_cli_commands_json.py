import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import pydmp.cli as cli
from pydmp.protocol import DMPProtocol, UserCode


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
    """Fake panel that routes bypass/restore NAK responses through the real
    DMPProtocol.decode_response(), so tests exercise the genuine NAK-detail path
    (PYDMP-023) rather than a stubbed `last_nak_detail`.
    """

    #: Set True on a subclass/instance to make `_send_command` return a genuine NAK.
    nak = False

    def __init__(self, *a, **k):
        self._protocol = DMPProtocol("1")

    async def connect(self, *a, **k):
        return None

    async def disconnect(self):
        return None

    async def disarm_areas(self, areas):
        return None

    async def _send_command(self, cmd, **kwargs):
        letter = "X" if "!X" in cmd else "Y" if "!Y" in cmd else "C"
        ack_nak = "-" if self.nak else "+"
        line = f"@    1{ack_nak}{letter}U"
        raw = ("\x02" + line + "\r").encode()
        return self._protocol.decode_response(raw)

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


@pytest.mark.parametrize("command", ["set-zone-bypass", "set-zone-restore"])
def test_cli_zone_bypass_restore_ack_json(monkeypatch, tmp_path, command):
    """ACK path (no NAK) succeeds for both bypass and restore."""
    cfg = _cfg(tmp_path)
    runner = CliRunner()

    monkeypatch.setattr(cli, "DMPPanel", _Panel)  # nak=False by default
    res = runner.invoke(cli.cli, ["-c", str(cfg), command, "5", "--json"])
    assert res.exit_code == 0
    assert json.loads(res.output)["ok"]


@pytest.mark.parametrize(
    ("command", "expect_phrase", "expect_detail"),
    [
        ("set-zone-bypass", "bypass zone", "(-XU)"),
        ("set-zone-restore", "restore zone", "(-YU)"),
    ],
)
def test_cli_zone_bypass_restore_nak_json(monkeypatch, tmp_path, command, expect_phrase, expect_detail):
    """NAK path is decoded via the real DMPProtocol.decode_response() and the
    '(-XU)'/'(undefined)' detail rendering (cli.py ~319-330/358-369) is exercised genuinely
    (PYDMP-023), not through a stubbed last_nak_detail.
    """
    cfg = _cfg(tmp_path)
    runner = CliRunner()

    class NakPanel(_Panel):
        nak = True

    monkeypatch.setattr(cli, "DMPPanel", NakPanel)
    res = runner.invoke(cli.cli, ["-c", str(cfg), command, "5", "--json"])
    assert res.exit_code != 0
    data = json.loads(res.output)
    assert not data["ok"]
    assert expect_phrase in data["error"]
    assert expect_detail in data["error"]
    assert "(undefined)" in data["error"]


def test_cli_sensor_and_check_code_json(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "DMPPanel", _Panel)
    runner = CliRunner()

    # sensor reset
    r = runner.invoke(cli.cli, ["-c", str(cfg), "sensor-reset", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.output)["ok"]

    # check-code found
    r2 = runner.invoke(cli.cli, ["-c", str(cfg), "check-code", "--code", "1234", "--json"])
    assert r2.exit_code == 0
    d = json.loads(r2.output)
    assert d["ok"] and d["found"] and d["user"]["number"] == "0001"
    # not found
    r3 = runner.invoke(cli.cli, ["-c", str(cfg), "check-code", "--code", "9999", "--json"])
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
