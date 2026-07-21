import json

import pytest
from click.testing import CliRunner

import pydmp.cli as cli
from pydmp.protocol import DMPProtocol
from tests.fakes import ConfigFactory, MinimalPanel, PanelResponse


class _Out:
    def __init__(self, num: int) -> None:
        self.number = num
        self.name = f"Output {num}"
        self._state = ""

    def to_dict(self) -> dict[str, object]:
        return {"number": self.number, "name": self.name, "state": self._state}

    async def turn_on(self) -> None:
        self._state = "ON"

    async def turn_off(self) -> None:
        self._state = "OF"

    async def pulse(self) -> None:
        self._state = "PL"

    async def toggle(self) -> None:
        self._state = "TP"


class _Panel(MinimalPanel):
    """Fake panel that routes bypass/restore NAK responses through the real
    DMPProtocol.decode_response(), so tests exercise the genuine NAK-detail path
    (PYDMP-023) rather than a stubbed `last_nak_detail`.
    """

    #: Set True on a subclass/instance to make `_send_command` return a genuine NAK.
    nak = False

    def __init__(self, port: int = 2011, timeout: float = 10.0) -> None:
        super().__init__(port, timeout)
        self._protocol = DMPProtocol("1")

    async def _send_command(self, command: str, **kwargs: object) -> PanelResponse:
        del kwargs
        letter = "X" if "!X" in command else "Y" if "!Y" in command else "C"
        ack_nak = "-" if self.nak else "+"
        line = f"@    1{ack_nak}{letter}U"
        raw = ("\x02" + line + "\r").encode()
        return self._protocol.decode_response(raw)

    async def update_output_status(self) -> None:
        return None

    async def get_outputs(self) -> list[_Out]:
        o = _Out(1)
        o._state = "ON"
        return [o]

    async def get_output(self, n: int) -> _Out:
        return _Out(n)


def test_cli_output_text(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    class Out:
        def __init__(self, n: int) -> None:
            self.number = n
            self._state = "OF"

        async def pulse(self) -> None:  # noqa: D401
            self._state = "PL"

        async def toggle(self) -> None:  # noqa: D401
            self._state = "TP"

        async def turn_on(self) -> None:  # noqa: D401
            self._state = "ON"

        async def turn_off(self) -> None:  # noqa: D401
            self._state = "OF"

    class P(MinimalPanel):
        async def get_output(self, n: int) -> Out:
            return Out(n)

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-output", "3", "pulse"])  # text
    assert r.exit_code == 0 and "Setting output 3 to pulse" in r.output


def test_cli_output_json(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    """JSON-mode output command returns a payload describing the applied mode."""
    cfg = cli_cfg()
    monkeypatch.setattr(cli, "DMPPanel", _Panel)
    res = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-output", "1", "on", "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.output)
    assert payload["ok"] and payload["output"] == 1 and payload["mode"] == "on"


def test_cli_output_error_json(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    cfg = cli_cfg()

    class OutputStub(_Out):
        async def turn_on(self) -> None:
            from pydmp.exceptions import DMPOutputError

            raise DMPOutputError("fail")

    class P(_Panel):
        async def get_output(self, n: int) -> _Out:
            return OutputStub(n)

    monkeypatch.setattr(cli, "DMPPanel", P)
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-output", "1", "on", "--json"])
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert not data["ok"] and "fail" in data["error"]


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("command", ["set-zone-bypass", "set-zone-restore"])
def test_cli_zone_bypass_restore_ack(
    monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory, command: str, as_json: bool
) -> None:
    """ACK path (no NAK) succeeds for both bypass and restore, text and JSON."""
    cfg = cli_cfg()
    monkeypatch.setattr(cli, "DMPPanel", _Panel)  # nak=False by default
    args = ["-c", str(cfg), command, "5"] + (["--json"] if as_json else [])
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 0
    if as_json:
        assert json.loads(res.output)["ok"]


def test_cli_zone_bypass_text_success(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
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
def test_cli_zone_bypass_restore_nak_json(
    monkeypatch: pytest.MonkeyPatch,
    cli_cfg: ConfigFactory,
    command: str,
    expect_phrase: str,
    expect_detail: str,
) -> None:
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


def test_cli_zone_restore_text_nak_detail(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    """Restore failure with a stubbed NAK detail exercises the text-mode error path."""
    cfg = cli_cfg()

    class P2(_Panel):
        def __init__(self, port: int = 2011, timeout: float = 10.0) -> None:
            super().__init__(port, timeout)
            self._protocol.last_nak_detail = "XU"

        async def _send_command(self, command: str, **kwargs: object) -> str:
            del command, kwargs
            return "NAK"

    monkeypatch.setattr(cli, "DMPPanel", P2)
    r2 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-zone-restore", "9"])  # text error
    assert r2.exit_code != 0 and "restore zone" in r2.output
