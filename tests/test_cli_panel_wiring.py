"""PYDMP-009 / PYDMP-010: every CLI command must pass configured port/timeout through to
DMPPanel, and every command that talks to the panel must emit the same {"ok": false, "error":
...} JSON error contract (or a clean text-mode error) on failure instead of leaking a traceback.
"""

import json
from typing import Any

import pytest
from click.testing import CliRunner

import pydmp.cli as cli

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
def test_cli_commands_propagate_configured_port_and_timeout(
    monkeypatch: Any, cli_cfg: Any, command: Any, extra_args: Any
) -> None:
    recorded = {}

    class RecordingPanel:
        def __init__(self, *a: Any, port: Any = None, timeout: Any = None, **k: Any) -> None:
            recorded["port"] = port
            recorded["timeout"] = timeout

        async def connect(self, *a: Any, **k: Any) -> Any:
            return None

        async def disconnect(self) -> Any:
            return None

        async def arm_areas(self, *a: Any, **k: Any) -> Any:
            return None

        async def _send_command(self, *a: Any, **k: Any) -> Any:
            return "ACK"

        async def get_user_codes(self) -> Any:
            return []

        async def get_user_profiles(self) -> Any:
            return []

        async def update_output_status(self) -> Any:
            return None

        async def get_outputs(self) -> Any:
            return []

        async def sensor_reset(self) -> Any:
            return None

        async def check_code(self, code: Any, include_pin: Any = True) -> Any:
            return None

    monkeypatch.setattr(cli, "DMPPanel", RecordingPanel)
    cfg = cli_cfg(port=4242, timeout=7.5)
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
def test_cli_commands_emit_json_error_contract_on_failure(
    monkeypatch: Any, cli_cfg: Any, command: Any, extra_args: Any
) -> None:
    class FailingPanel:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def connect(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("boom")

        async def disconnect(self) -> Any:
            return None

    monkeypatch.setattr(cli, "DMPPanel", FailingPanel)
    cfg = cli_cfg()
    result = CliRunner().invoke(cli.cli, ["-c", str(cfg), command, *extra_args])

    assert result.exit_code != 0
    data = json.loads(result.output)
    assert data == {"ok": False, "error": "boom"}


def test_cli_set_output_text_mode_error_is_clean(monkeypatch: Any, cli_cfg: Any) -> None:
    """set-output (deprecated alias) failures still print a clean error, not a traceback."""

    class FailingPanel:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def connect(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("boom")

        async def disconnect(self) -> Any:
            return None

    monkeypatch.setattr(cli, "DMPPanel", FailingPanel)
    cfg = cli_cfg()
    result = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-output", "1", "on"])

    assert result.exit_code != 0
    assert result.exc_info is None or result.exc_info[0] in (SystemExit, None)
    assert "boom" in result.output
    assert "Traceback" not in result.output


def test_cli_output_is_hidden_deprecated_alias(monkeypatch: Any, cli_cfg: Any) -> None:
    """'output' is hidden from help, forwards to 'set-output' (incl. --json), warns on stderr."""
    import re

    help_result = CliRunner().invoke(cli.cli, ["--help"])
    assert "set-output" in help_result.output
    assert not re.search(r"^\s+output\b", help_result.output, re.MULTILINE)

    calls = {}

    class Out:
        async def turn_on(self) -> None:
            calls["on"] = True

    class Panel:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def connect(self, *a: Any, **k: Any) -> Any:
            return None

        async def disconnect(self) -> Any:
            return None

        async def get_output(self, n: Any) -> Any:
            calls["output"] = n
            return Out()

    monkeypatch.setattr(cli, "DMPPanel", Panel)
    cfg = cli_cfg()
    result = CliRunner().invoke(cli.cli, ["-c", str(cfg), "output", "1", "on", "--json"])

    assert result.exit_code == 0
    assert calls == {"output": 1, "on": True}
    assert json.loads(result.stdout) == {"ok": True, "action": "output", "output": 1, "mode": "on"}
    assert "deprecated" in result.stderr.lower()
