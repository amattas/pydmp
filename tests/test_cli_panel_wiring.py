"""PYDMP-009 / PYDMP-010: every CLI command must pass configured port/timeout through to
DMPPanel, and every command that talks to the panel must emit the same {"ok": false, "error":
...} JSON error contract (or a clean text-mode error) on failure instead of leaking a traceback.
"""

import json

import pytest
from click.testing import CliRunner

import pydmp.cli as cli
from pydmp.output import Output
from pydmp.profile import UserProfile
from pydmp.user import UserCode
from tests.fakes import ConfigFactory, MinimalPanel

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
    monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory, command: str, extra_args: list[str]
) -> None:
    recorded: dict[str, object] = {}

    class RecordingPanel(MinimalPanel):
        def __init__(self, port: int = 2011, timeout: float = 10.0) -> None:
            super().__init__(port, timeout)
            recorded["port"] = port
            recorded["timeout"] = timeout

        async def arm_areas(self, areas: list[int], **kwargs: object) -> None:
            del areas, kwargs
            return None

        async def _send_command(self, command: str, **kwargs: object) -> str:
            del command, kwargs
            return "ACK"

        async def get_user_codes(self) -> list[UserCode]:
            return []

        async def get_user_profiles(self) -> list[UserProfile]:
            return []

        async def update_output_status(self) -> None:
            return None

        async def get_outputs(self) -> list[Output]:
            return []

        async def sensor_reset(self) -> None:
            return None

        async def check_code(self, code: str, include_pin: bool = True) -> UserCode | None:
            del code, include_pin
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
    monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory, command: str, extra_args: list[str]
) -> None:
    class FailingPanel(MinimalPanel):
        async def connect(self, host: str, account_number: str, remote_key: str) -> None:
            del host, account_number, remote_key
            raise RuntimeError("boom")

    monkeypatch.setattr(cli, "DMPPanel", FailingPanel)
    cfg = cli_cfg()
    result = CliRunner().invoke(cli.cli, ["-c", str(cfg), command, *extra_args])

    assert result.exit_code != 0
    data = json.loads(result.output)
    assert data == {"ok": False, "error": "boom"}


def test_cli_set_output_text_mode_error_is_clean(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    """set-output (deprecated alias) failures still print a clean error, not a traceback."""

    class FailingPanel(MinimalPanel):
        async def connect(self, host: str, account_number: str, remote_key: str) -> None:
            del host, account_number, remote_key
            raise RuntimeError("boom")

    monkeypatch.setattr(cli, "DMPPanel", FailingPanel)
    cfg = cli_cfg()
    result = CliRunner().invoke(cli.cli, ["-c", str(cfg), "set-output", "1", "on"])

    assert result.exit_code != 0
    assert result.exc_info is None or result.exc_info[0] in (SystemExit, None)
    assert "boom" in result.output
    assert "Traceback" not in result.output


def test_cli_output_is_hidden_deprecated_alias(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    """'output' is hidden from help, forwards to 'set-output' (incl. --json), warns on stderr."""
    import re

    help_result = CliRunner().invoke(cli.cli, ["--help"])
    assert "set-output" in help_result.output
    assert not re.search(r"^\s+output\b", help_result.output, re.MULTILINE)

    calls: dict[str, object] = {}

    class Out:
        async def turn_on(self) -> None:
            calls["on"] = True

    class Panel(MinimalPanel):
        async def get_output(self, n: int) -> Out:
            calls["output"] = n
            return Out()

    monkeypatch.setattr(cli, "DMPPanel", Panel)
    cfg = cli_cfg()
    result = CliRunner().invoke(cli.cli, ["-c", str(cfg), "output", "1", "on", "--json"])

    assert result.exit_code == 0
    assert calls == {"output": 1, "on": True}
    assert json.loads(result.stdout) == {"ok": True, "action": "output", "output": 1, "mode": "on"}
    assert "deprecated" in result.stderr.lower()
