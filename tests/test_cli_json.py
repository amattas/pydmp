import json

import pytest
from click.testing import CliRunner

import pydmp.cli as cli
from pydmp.profile import UserProfile
from pydmp.user import UserCode
from tests.fakes import ConfigFactory, MinimalPanel


def test_cli_arm_json(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    recorded: dict[str, object] = {}

    class P(MinimalPanel):
        async def arm_areas(
            self,
            areas: list[int] | tuple[int, ...],
            bypass_faulted: bool = False,
            force_arm: bool = False,
            instant: bool | None = None,
        ) -> None:
            recorded["areas"] = list(areas)
            recorded["bypass"] = bypass_faulted
            recorded["force"] = force_arm
            recorded["instant"] = instant

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r = CliRunner().invoke(
        cli.cli,
        ["-c", str(cfg), "arm", "1,2", "--bypass-faulted", "--no-instant", "--json"],
    )
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert payload["ok"] and payload["areas"] == [1, 2]
    assert recorded == {"areas": [1, 2], "bypass": True, "force": False, "instant": False}


def test_cli_get_outputs_json(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    class OutputStub:
        def __init__(self, n: int) -> None:
            self.number = n
            self.name = f"Out{n}"
            self._state = "ON"

        def to_dict(self) -> dict[str, object]:
            return {"number": self.number, "name": self.name, "state": self._state}

    class P(MinimalPanel):
        async def update_output_status(self) -> None:
            return None

        async def get_outputs(self) -> list[OutputStub]:
            return [OutputStub(1), OutputStub(2)]

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "get-outputs", "--json"])
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["ok"] and len(data["outputs"]) == 2


def test_cli_disarm_error_json(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    class P(MinimalPanel):
        async def disarm_areas(self, areas: list[int] | tuple[int, ...]) -> None:
            del areas
            raise Exception("cannot disarm")

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "disarm", "1", "--json"])
    assert r.exit_code != 0
    # Ensure the error reason is surfaced
    assert "cannot disarm" in r.output


def test_cli_disarm_json_success(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    class P(MinimalPanel):
        async def disarm_areas(self, areas: list[int] | tuple[int, ...]) -> None:
            del areas

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "disarm", "1", "--json"])
    assert r.exit_code == 0


def test_cli_get_areas_json(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    class A:
        def __init__(self, n: int) -> None:
            self.number = n

        def to_dict(self) -> dict[str, object]:
            return {"number": self.number, "name": f"Area {self.number}", "state": "D"}

    class P(MinimalPanel):
        async def update_status(self) -> None:
            return None

        async def get_areas(self) -> list[A]:
            return [A(1), A(2)]

    cfg = cli_cfg()
    monkeypatch.setattr(cli, "DMPPanel", P)
    runner = CliRunner()
    res = runner.invoke(cli.cli, ["--config", str(cfg), "get-areas", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["ok"] and len(data["areas"]) == 2


def _make_users_profiles_panel() -> type[MinimalPanel]:
    class P(MinimalPanel):
        async def get_user_codes(self) -> list[UserCode]:
            return [
                UserCode(
                    number="0001",
                    code="1234",
                    pin="",
                    profiles=("001", "002", "003", "004"),
                    temp_date="010125",
                    exp_date="0900",
                    start_date="010125",
                    end_date="310125",
                    flags="YYN",
                    active=True,
                    temporary=False,
                    name="USER",
                )
            ]

        async def get_user_profiles(self) -> list[UserProfile]:
            return [
                UserProfile(
                    number="001",
                    areas_mask="C3000000",
                    access_areas_mask="C3000000",
                    output_group="001",
                    menu_options="MENUOPTS",
                    rearm_delay="005",
                    name="ADMIN",
                )
            ]

    return P


@pytest.mark.parametrize(
    ("command", "key", "expected_text", "expected_value"),
    [
        ("get-users", "users", "Users", "0001"),
        ("get-profiles", "profiles", "Profiles", "001"),
    ],
)
@pytest.mark.parametrize("as_json", [False, True])
def test_cli_get_users_profiles(
    monkeypatch: pytest.MonkeyPatch,
    cli_cfg: ConfigFactory,
    as_json: bool,
    command: str,
    key: str,
    expected_text: str,
    expected_value: str,
) -> None:
    monkeypatch.setattr(cli, "DMPPanel", _make_users_profiles_panel())
    cfg = cli_cfg()
    args = ["-c", str(cfg), command] + (["--json"] if as_json else [])
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 0
    if as_json:
        data = json.loads(res.output)[key]
        assert data and data[0]["number"] == expected_value
    else:
        assert expected_text in res.output


def _make_check_code_panel() -> type[MinimalPanel]:
    class P(MinimalPanel):
        async def check_code(self, code: str, include_pin: bool = True) -> UserCode | None:
            del include_pin
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

    return P


@pytest.mark.parametrize(
    ("code", "found"),
    [
        ("1234", True),
        ("9999", False),
    ],
)
@pytest.mark.parametrize("as_json", [False, True])
def test_cli_check_code(
    monkeypatch: pytest.MonkeyPatch,
    cli_cfg: ConfigFactory,
    as_json: bool,
    code: str,
    found: bool,
) -> None:
    monkeypatch.setattr(cli, "DMPPanel", _make_check_code_panel())
    cfg = cli_cfg()
    args = ["-c", str(cfg), "check-code", "--code", code] + (["--json"] if as_json else [])
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 0
    if as_json:
        data = json.loads(res.output)
        assert data["ok"] and data["found"] is found
        if found:
            assert data["user"]["number"] == "0001"
        else:
            assert data["user"] is None
    else:
        assert ("Match" in res.output) if found else ("No match" in res.output)


def test_cli_check_code_prompts_for_code(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    """PYDMP-015: code is no longer a positional argv argument; it is prompted securely."""
    monkeypatch.setattr(cli, "DMPPanel", _make_check_code_panel())
    cfg = cli_cfg()
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "check-code"], input="1234\n")
    assert r.exit_code == 0 and "Match" in r.output


def test_cli_sensor_reset_json(monkeypatch: pytest.MonkeyPatch, cli_cfg: ConfigFactory) -> None:
    class P(MinimalPanel):
        async def sensor_reset(self) -> None:
            return None

    monkeypatch.setattr(cli, "DMPPanel", P)
    cfg = cli_cfg()
    r = CliRunner().invoke(cli.cli, ["-c", str(cfg), "sensor-reset", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.output)["ok"]
