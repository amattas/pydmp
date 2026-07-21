from typing import Any

from click.testing import CliRunner

import pydmp.cli as cli


def test_cli_help_sections() -> None:
    r = CliRunner().invoke(cli.cli, ["--help"])
    assert r.exit_code == 0
    assert "Panel Control" in r.output and "Status & Query" in r.output


def test_cli_text_arm_disarm_outputs_sensor(monkeypatch: Any, cli_cfg: Any) -> None:
    class P:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def connect(self, *a: Any, **k: Any) -> Any:
            return None

        async def disconnect(self) -> Any:
            return None

        async def arm_areas(self, areas: Any, **kw: Any) -> Any:
            return None

        async def disarm_areas(self, areas: Any) -> Any:
            return None

        async def update_output_status(self) -> Any:
            return None

        async def get_outputs(self) -> Any:
            class OutputStub:
                def __init__(self, n: Any) -> None:
                    self.number = n
                    self.name = f"Out{n}"
                    self._state = "ON"

                @property
                def state(self) -> Any:  # mimic Output.state
                    return self._state

                def to_dict(self) -> Any:
                    return {"number": self.number, "name": self.name, "state": self._state}

            return [OutputStub(1), OutputStub(2)]

        async def sensor_reset(self) -> Any:
            return None

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r1 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "arm", "1,2"])  # text mode
    assert r1.exit_code == 0 and "Arming areas" in r1.output

    r2 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "disarm", "1"])  # text mode
    assert r2.exit_code == 0 and "Disarming area" in r2.output

    r3 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "get-outputs"])  # table output
    assert r3.exit_code == 0 and "Outputs" in r3.output

    r4 = CliRunner().invoke(cli.cli, ["-c", str(cfg), "sensor-reset"])  # text mode
    assert r4.exit_code == 0 and "Sensor reset" in r4.output


def test_cli_config_yaml_parse_error(tmp_path: Any) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("panel: [1, 2")  # malformed YAML to trigger parser error
    out = CliRunner().invoke(cli.cli, ["-c", str(bad), "arm", "1"])
    assert out.exit_code != 0 and ("Error parsing config" in out.output or "Invalid config" in out.output)


def test_cli_config_invalid_shape(tmp_path: Any) -> None:
    # Invalid shape triggers invalid config message
    inv = tmp_path / "inv.yaml"
    inv.write_text("[1, 2, 3]")
    out2 = CliRunner().invoke(cli.cli, ["-c", str(inv), "arm", "1"])
    assert out2.exit_code != 0 and "Invalid config" in out2.output


def test_cli_debug_flag_executes(monkeypatch: Any, cli_cfg: Any) -> None:
    class P:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def connect(self, *a: Any, **k: Any) -> Any:
            return None

        async def disconnect(self) -> Any:
            return None

        async def arm_areas(self, *a: Any, **k: Any) -> Any:
            return None

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r = CliRunner().invoke(cli.cli, ["-d", "-c", str(cfg), "arm", "1"])  # debug flag
    assert r.exit_code == 0
