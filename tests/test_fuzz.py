"""Fuzz-corpus replay and property tests for the parsers that read panel-originated data.

The atheris targets in ``fuzz/`` cover the byte/framing paths; every PR replays their
seed corpus (and any fixed crash inputs) here without the fuzz engine. Each target's
``TestOneInput`` raises only the exception types documented for that entry point, so the
replay asserts the same contract the fuzzer enforces. The line parsers are covered by
Hypothesis properties below.
"""

from __future__ import annotations

import functools
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pydmp.const.protocol import ZONE_DELIMITER
from pydmp.const.responses import (
    AREA_STATUS_ARMED_AWAY,
    AREA_STATUS_ARMED_STAY,
    AREA_STATUS_DISARMED,
    ZONE_STATUS_BYPASSED,
    ZONE_STATUS_LOW_BATTERY,
    ZONE_STATUS_MISSING,
    ZONE_STATUS_NORMAL,
    ZONE_STATUS_OPEN,
    ZONE_STATUS_SHORT,
)
from pydmp.protocol import DMPProtocol, StatusResponse
from pydmp.status_parser import parse_s3_message
from pydmp.status_server import DMPStatusServer, S3Message

FUZZ_DIR = Path(__file__).resolve().parents[1] / "fuzz"
CORPUS_DIR = FUZZ_DIR / "corpus"


@functools.cache
def _load_target(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, FUZZ_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CORPUS = sorted(p for p in CORPUS_DIR.glob("*/*") if p.is_file())


def test_every_target_has_seeds() -> None:
    targets = {p.stem for p in FUZZ_DIR.glob("fuzz_*.py")}
    assert targets, "no fuzz targets found"
    assert targets == {p.parent.name for p in CORPUS}


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_corpus_replay(path: Path) -> None:
    # TestOneInput lets only documented exceptions through; anything else fails here.
    _load_target(path.parent.name).TestOneInput(path.read_bytes())


AREA_STATES = {
    AREA_STATUS_ARMED_AWAY,
    AREA_STATUS_DISARMED,
    AREA_STATUS_ARMED_STAY,
    "unknown",
}
ZONE_STATES = {
    ZONE_STATUS_NORMAL,
    ZONE_STATUS_OPEN,
    ZONE_STATUS_SHORT,
    ZONE_STATUS_BYPASSED,
    ZONE_STATUS_LOW_BATTERY,
    ZONE_STATUS_MISSING,
    "unknown",
}

# Bias generated text toward the characters these parsers branch on.
_protocol_text = st.text(
    alphabet=st.one_of(
        st.sampled_from(["A", "L", "Z", "t", " ", '"', "\\", ZONE_DELIMITER, "\r", "-"]),
        st.characters(),
    ),
    max_size=200,
)


@given(z_body=_protocol_text, account=st.one_of(st.none(), st.text(max_size=8)))
def test_parse_z_body_properties(z_body: str, account: str | None) -> None:
    msg = DMPStatusServer._parse_z_body(account, z_body)
    assert msg.raw == z_body
    assert "\\".join(msg.fields) == z_body
    assert msg.definition == z_body[:2]
    assert msg.account == (account or "").strip()
    assert msg.type_code is None or " " not in msg.type_code


@given(
    definition=st.one_of(st.sampled_from(["Za", "Zc", "Zq", "Zs", "Zl", "Zd", "Zu"]), st.text(max_size=3)),
    type_code=st.one_of(st.none(), st.text(max_size=4)),
    fields=st.lists(_protocol_text, max_size=8),
)
def test_parse_s3_message_properties(definition: str, type_code: str | None, fields: list[str]) -> None:
    msg = S3Message(
        account="00001",
        definition=definition,
        type_code=type_code,
        fields=fields,
        raw="",
    )
    evt = parse_s3_message(msg)
    assert evt.fields is fields
    assert evt.type_code == type_code
    assert evt.category is None or evt.category.value == definition
    assert evt.code_enum is None or evt.category is not None


@given(status_data=_protocol_text)
def test_parse_status_line_properties(status_data: str) -> None:
    response = StatusResponse(areas={}, zones={})
    DMPProtocol("1", "")._parse_status_line(status_data, response)
    assert all(a.state in AREA_STATES and a.number == key for key, a in response.areas.items())
    assert all(z.state in ZONE_STATES and z.number == key for key, z in response.zones.items())
