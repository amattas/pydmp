import json
from dataclasses import dataclass

from click.testing import CliRunner

import pydmp.cli as cli


def test_cli_listen_json(monkeypatch):
    # Fake server triggers one callback and returns
    class Srv:
        def __init__(self, host, port):
            self.cb = None

        def register_callback(self, cb):
            self.cb = cb

        async def start(self):
            if self.cb:

                @dataclass
                class Evt:
                    category: str = "Zc"
                    type_code: str = "ON"
                    area: str = "1"
                    zone: str = "2"
                    device: str = "3"
                    system_text: str = "OK"

                self.cb(object())  # parse will create the event below

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
        cli,
        "parse_s3_message",
        lambda msg: Parsed("Zc", "ON", "1", "2", "3", "OK"),
    )

    async def no_sleep(_):
        return None

    monkeypatch.setattr(cli.asyncio, "sleep", no_sleep)

    res = CliRunner().invoke(cli.cli, ["listen", "--json", "--duration", "1"])
    assert res.exit_code == 0
    # Should be a single JSON line
    obj = json.loads(res.output.strip())
    assert obj["category"] == "Zc" and obj["type_code"] == "ON"
