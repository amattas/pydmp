import logging

from pydmp.const.commands import DMPCommand
from pydmp.const.protocol import RESPONSE_DELIMITER
from pydmp.protocol import DMPProtocol, OutputsResponse, StatusResponse


def _frame(body: str) -> bytes:
    return f"{RESPONSE_DELIMITER}@    1{body}\r".encode()


def test_encode_command_redacts_remote_key(caplog):
    p = DMPProtocol("1", "S3CRETKEY")
    with caplog.at_level(logging.DEBUG, logger="pydmp.protocol"):
        frame = p.encode_command(DMPCommand.AUTH.value, key="S3CRETKEY")
    # The wire frame itself must still carry the real key.
    assert b"!V2S3CRETKEY" in frame
    # But it must never appear in the logs.
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "S3CRETKEY" not in logged
    assert "!V2<redacted>" in logged


def test_decode_nak_detail():
    p = DMPProtocol("1", "")

    # NAK with detail -XU
    res = p.decode_response(_frame("-XU"))
    assert res == "NAK" and p.last_nak_detail == "XU"


def test_decode_unknown_states():
    p = DMPProtocol("1", "")

    # Area with unknown state
    sr = p.decode_response(_frame("+!WBA  1ZAreaOne\x1e-"))
    assert isinstance(sr, StatusResponse)
    assert sr.areas["1"].state == "unknown"

    # Zones unknown state
    sr2 = p.decode_response(_frame("+!WBL001ZFront\x1e-"))
    assert isinstance(sr2, StatusResponse)
    assert sr2.zones["001"].state == "unknown"


def test_empty_status_segments():
    p = DMPProtocol("1", "")
    # Empty WB
    sr = p.decode_response(_frame("+!WB-"))
    assert isinstance(sr, StatusResponse)
    assert not sr.areas and not sr.zones


def test_output_status_decode():
    p = DMPProtocol("1", "")
    # Output status single item
    orsp = p.decode_response(_frame("+*WQ001SRelay1\x1e-"))
    assert isinstance(orsp, OutputsResponse)
    assert orsp.outputs["001"].mode == "S" and orsp.outputs["001"].name == "Relay1"


def test_user_profiles_short_record_name_fallback():
    p = DMPProtocol("1", "")
    # Short record (<49 chars) should use name from index 30+
    item = "001" + "C3000000" + "C3000000" + "001" + "MENUOPTS" + "SHORTNAME"
    resp = p.decode_response(_frame("+*U" + item + "\x1e-"))
    from pydmp.protocol import UserProfilesResponse

    assert isinstance(resp, UserProfilesResponse)
    assert resp.profiles and resp.profiles[0].name.endswith("SHORTNAME")
