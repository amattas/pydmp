import json
from dataclasses import dataclass

import pytest
from click.testing import CliRunner

import pydmp.cli as cli


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_listen(monkeypatch, as_json):
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

    args = ["listen", "--duration", "1"]
    if as_json:
        args.insert(1, "--json")
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 0

    if as_json:
        # Should be a single JSON line
        obj = json.loads(res.output.strip())
        assert obj["category"] == "Zc" and obj["type_code"] == "ON"
    else:
        assert "Zc" in res.output and "ON" in res.output and "a=1" in res.output
