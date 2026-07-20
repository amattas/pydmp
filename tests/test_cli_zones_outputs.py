import json

import pytest
from click.testing import CliRunner

import pydmp.cli as cli
from pydmp.protocol import DMPProtocol


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


def test_cli_output_text(monkeypatch, cli_cfg):
    class Out:
        def __init__(self, n):
            self.number = n
            self._state = "OF"

        async def pulse(self):  # noqa: D401
            self._state = "PL"

        async def toggle(self):  # noqa: D401
            self._state = "TP"

        async def turn_on(self):  # noqa: D401
            self._state = "ON"

        async def turn_off(self):  # noqa: D401
            self._state = "OF"

    class P:
        def __init__(self, *a, **k):
            pass

        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def get_output(self, n: int):
            return Out(n)

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-output", "3", "pulse"])  # text
    assert r.exit_code == 0 and "Setting output 3 to pulse" in r.output


def test_cli_output_json(monkeypatch, cli_cfg):
    """JSON-mode output command returns a payload describing the applied mode."""
    cfg = cli_cfg()
    monkeypatch.setattr(cli, "DMPPanel", _Panel)
    res = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-output", "1", "on", "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.output)
    assert payload["ok"] and payload["output"] == 1 and payload["mode"] == "on"


def test_cli_output_error_json(monkeypatch, cli_cfg):
    cfg = cli_cfg()

    class P(_Panel):
        async def get_output(self, n: int):
            class OutputStub:
                async def turn_on(self):
                    from pydmp.exceptions import DMPOutputError

                    raise DMPOutputError("fail")

            return OutputStub()

    monkeypatch.setattr(cli, "DMPPanel", P)
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-output", "1", "on", "--json"])
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert not data["ok"] and "fail" in data["error"]


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("command", ["set-zone-bypass", "set-zone-restore"])
def test_cli_zone_bypass_restore_ack(monkeypatch, cli_cfg, command, as_json):
    """ACK path (no NAK) succeeds for both bypass and restore, text and JSON."""
    cfg = cli_cfg()
    monkeypatch.setattr(cli, "DMPPanel", _Panel)  # nak=False by default
    args = ["-c", str(cfg), command, "5"] + (["--json"] if as_json else [])
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 0
    if as_json:
        assert json.loads(res.output)["ok"]


def test_cli_zone_bypass_text_success(monkeypatch, cli_cfg):
    cfg = cli_cfg()
    monkeypatch.setattr(cli, "DMPPanel", _Panel)
    r1 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-zone-bypass", "5"])  # text
    assert r1.exit_code == 0 and "bypassed" in r1.output


@pytest.mark.parametrize(
    ("command", "expect_phrase", "expect_detail"),
    [
        ("set-zone-bypass", "bypass zone", "(-XU)"),
        ("set-zone-restore", "restore zone", "(-YU)"),
    ],
)
def test_cli_zone_bypass_restore_nak_json(monkeypatch, cli_cfg, command, expect_phrase, expect_detail):
    """NAK path is decoded via the real DMPProtocol.decode_response() and the
    '(-XU)'/'(undefined)' detail rendering (cli.py ~319-330/358-369) is exercised genuinely
    (PYDMP-023), not through a stubbed last_nak_detail.
    """
    cfg = cli_cfg()

    class NakPanel(_Panel):
        nak = True

    monkeypatch.setattr(cli, "DMPPanel", NakPanel)
    res = CliRunner().invoke(cli.cli, ["-c", str(cfg), command, "5", "--json"])
    assert res.exit_code != 0
    data = json.loads(res.output)
    assert not data["ok"]
    assert expect_phrase in data["error"]
    assert expect_detail in data["error"]
    assert "(undefined)" in data["error"]


def test_cli_zone_restore_text_nak_detail(monkeypatch, cli_cfg):
    """Restore failure with a stubbed NAK detail exercises the text-mode error path."""
    cfg = cli_cfg()

    class P2:
        def __init__(self, *a, **k):
            self._protocol = type("Prot", (), {"last_nak_detail": "XU"})()

        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def _send_command(self, *a, **k):
            return "NAK"

    monkeypatch.setattr(cli, "DMPPanel", P2)
    r2 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-zone-restore", "9"])  # text error
    assert r2.exit_code != 0 and "restore zone" in r2.output
