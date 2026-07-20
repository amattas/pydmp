"""PYDMP-009 / PYDMP-010: every CLI command must pass configured port/timeout through to
DMPPanel, and every command that talks to the panel must emit the same {"ok": false, "error":
...} JSON error contract (or a clean text-mode error) on failure instead of leaking a traceback.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import pydmp.cli as cli


def _cfg(tmp_path: Path, port: int = 4242, timeout: float = 7.5) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(f"panel:\n  host: h\n  account: '1'\n  remote_key: 'K'\n  port: {port}\n  timeout: {timeout}\n")
    return p


# Commands (with a minimal valid argv tail) that PYDMP-009 found constructing DMPPanel() bare.
_BARE_PANEL_COMMANDS = [
    ("arm", ["1"]),
    ("set-zone-bypass", ["5"]),
    ("set-zone-restore", ["5"]),
    ("get-users", []),
    ("get-profiles", []),
    ("get-outputs", []),
    ("sensor-reset", []),
    ("check-code", ["--code", "1234"]),
]


@pytest.mark.parametrize(("command", "extra_args"), _BARE_PANEL_COMMANDS)
def test_cli_commands_propagate_configured_port_and_timeout(monkeypatch, tmp_path, command, extra_args):
    recorded = {}

    class RecordingPanel:
        def __init__(self, *a, port=None, timeout=None, **k):
            recorded["port"] = port
            recorded["timeout"] = timeout

        async def connect(self, *a, **k):
            return None

        async def disconnect(self):
            return None

        async def arm_areas(self, *a, **k):
            return None

        async def _send_command(self, *a, **k):
            return "ACK"

        async def get_user_codes(self):
            return []

        async def get_user_profiles(self):
            return []

        async def update_output_status(self):
            return None

        async def get_outputs(self):
            return []

        async def sensor_reset(self):
            return None

        async def check_code(self, code, include_pin=True):
            return None

    monkeypatch.setattr(cli, "DMPPanel", RecordingPanel)
    cfg = _cfg(tmp_path, port=4242, timeout=7.5)
    result = CliRunner().invoke(cli.cli, ["-c", str(cfg), command, *extra_args, "--json"])

    assert result.exit_code == 0, result.output
    assert recorded == {"port": 4242, "timeout": 7.5}


@pytest.mark.parametrize(
    ("command", "extra_args"),
    [
        ("arm", ["1", "--json"]),
        ("get-areas", ["--json"]),
        ("get-zones", ["--json"]),
    ],
)
def test_cli_commands_emit_json_error_contract_on_failure(monkeypatch, tmp_path, command, extra_args):
    class FailingPanel:
        def __init__(self, *a, **k):
            pass

        async def connect(self, *a, **k):
            raise RuntimeError("boom")

        async def disconnect(self):
            return None

    monkeypatch.setattr(cli, "DMPPanel", FailingPanel)
    cfg = _cfg(tmp_path)
    result = CliRunner().invoke(cli.cli, ["-c", str(cfg), command, *extra_args])

    assert result.exit_code != 0
    data = json.loads(result.output)
    assert data == {"ok": False, "error": "boom"}


def test_cli_set_output_text_mode_error_is_clean(monkeypatch, tmp_path):
    """set-output has no --json flag; a failure must still print a clean error, not a traceback."""

    class FailingPanel:
        def __init__(self, *a, **k):
            pass

        async def connect(self, *a, **k):
            raise RuntimeError("boom")

        async def disconnect(self):
            return None

    monkeypatch.setattr(cli, "DMPPanel", FailingPanel)
    cfg = _cfg(tmp_path)
    result = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-output", "1", "on"])

    assert result.exit_code != 0
    assert result.exc_info is None or result.exc_info[0] in (SystemExit, None)
    assert "boom" in result.output
    assert "Traceback" not in result.output
