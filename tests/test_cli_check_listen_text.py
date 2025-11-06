from dataclasses import dataclass
from pathlib import Path

from click.testing import CliRunner

import pydmp.cli as cli


def _cfg(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "panel:\n  host: h\n  account: '1'\n  remote_key: 'K'\n  port: 2011\n  timeout: 1\n"
    )
    return p


def test_cli_check_code_text(monkeypatch, tmp_path):
    class P:
        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def check_code(self, code: str, include_pin: bool = True):
            from pydmp.protocol import UserCode

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

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = _cfg(tmp_path)
    r1 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "check-code", "1234"])  # text found
    assert r1.exit_code == 0 and "Match" in r1.output
    r2 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "check-code", "9999"])  # text not found
    assert r2.exit_code == 0 and "No match" in r2.output


def test_cli_listen_text(monkeypatch):
    # Fake server that invokes callback once on start
    class Srv:
        def __init__(self, host, port):
            self.cb = None

        def register_callback(self, cb):
            self.cb = cb

        async def start(self):
            if self.cb:
                self.cb(object())

        async def stop(self):
            return None

    monkeypatch.setattr(cli, "DMPStatusServer", Srv)

    @dataclass
    class Parsed:
        category: str
        type_code: str
        area: str
        zone: str
        device: str
        system_text: str

    monkeypatch.setattr(
        cli, "parse_s3_message", lambda msg: Parsed("Zc", "ON", "1", "2", "3", "OK")
    )

    async def no_sleep(_):
        return None

    monkeypatch.setattr(cli.asyncio, "sleep", no_sleep)

    res = CliRunner().invoke(cli.cli, ["listen", "--duration", "1"])  # text mode
    assert res.exit_code == 0
    assert "Zc" in res.output and "ON" in res.output and "a=1" in res.output
