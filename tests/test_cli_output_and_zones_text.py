from pathlib import Path

from click.testing import CliRunner

import pydmp.cli as cli


def _cfg(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "panel:\n  host: h\n  account: '1'\n  remote_key: 'K'\n  port: 2011\n  timeout: 1\n"
    )
    return p


def test_cli_output_text(monkeypatch, tmp_path):
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
    cfg = _cfg(tmp_path)
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "output", "3", "pulse"])  # text
    assert r.exit_code == 0 and "Setting output 3 to pulse" in r.output


def test_cli_zone_bypass_restore_text_paths(monkeypatch, tmp_path):
    # Bypass success
    class P1:
        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def _send_command(self, *a, **k):
            return "ACK"

    monkeypatch.setattr(cli, "DMPPanel", P1)
    cfg = _cfg(tmp_path)
    r1 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-zone-bypass", "5"])  # text
    assert r1.exit_code == 0 and "bypassed" in r1.output

    # Restore failure with NAK detail present
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
