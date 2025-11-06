"""Tests to assert command payload formatting/lengths.

These validate that encoded commands match the expected Serial 3
wire format used by the panel: "@" + 5-char account + COMMAND + "\r".

They also ensure fixed-width numeric fields (area=2, zone=3, output=3)
are respected in example calls.
"""

import pytest

from pydmp.const.commands import DMPCommand
from pydmp.protocol import DMPProtocol


def _prot() -> DMPProtocol:
    # Account is left-padded to 5 chars
    return DMPProtocol("1", "TESTKEY")


@pytest.mark.parametrize(
    "cmd,kwargs,expected",
    [
        # Authentication and disconnect / keep-alive
        (DMPCommand.AUTH.value, {"key": "TESTKEY"}, "@    1!V2TESTKEY\r"),
        (DMPCommand.DISCONNECT.value, {}, "@    1!V0\r"),
        (DMPCommand.KEEP_ALIVE.value, {}, "@    1!H\r"),
        # System info
        (DMPCommand.GET_MAC.value, {}, "@    1?ZX1\r"),
        (DMPCommand.GET_SOFTWARE_VERSION.value, {}, "@    1? \r"),
        (DMPCommand.GET_SYSTEM_STATUS.value, {}, "@    1?WS\r"),
        # Area status (2-digit area) and continuation
        (DMPCommand.GET_AREA_STATUS.value, {"area": "01"}, "@    1?WA01\r"),
        (DMPCommand.GET_AREA_STATUS_CONT.value, {}, "@    1?WA\r"),
        # Output status (3-digit output) and continuation
        (DMPCommand.GET_OUTPUT_STATUS.value, {"output": "001"}, "@    1?WQ001\r"),
        (DMPCommand.GET_OUTPUT_STATUS_CONT.value, {}, "@    1?WQ\r"),
        # Zone status initial (3-digit zone) and continuation
        (DMPCommand.GET_ZONE_STATUS.value, {"zone": "001"}, "@    1?WB**Y001\r"),
        (DMPCommand.GET_ZONE_STATUS_CONT.value, {}, "@    1?WB\r"),
        # Area control: arm (2-digit area), with and without instant flag
        (
            DMPCommand.ARM.value,
            {"area": "01", "bypass": "N", "force": "N", "instant": ""},
            "@    1!C01,NN\r",
        ),
        (
            DMPCommand.ARM.value,
            {"area": "01", "bypass": "Y", "force": "N", "instant": "Y"},
            "@    1!C01,YNY\r",
        ),
        # Multi-area: concatenate two-digit areas
        (
            DMPCommand.ARM.value,
            {"area": "0102", "bypass": "N", "force": "N", "instant": ""},
            "@    1!C0102,NN\r",
        ),
        (DMPCommand.DISARM.value, {"area": "01"}, "@    1!O01\r"),
        (DMPCommand.DISARM.value, {"area": "0102"}, "@    1!O0102\r"),
        # Zone control (3-digit)
        (DMPCommand.BYPASS_ZONE.value, {"zone": "001"}, "@    1!X001\r"),
        (DMPCommand.RESTORE_ZONE.value, {"zone": "001"}, "@    1!Y001\r"),
        (DMPCommand.SENSOR_RESET.value, {}, "@    1!E001\r"),
        # Output control (3-digit + mode)
        (DMPCommand.OUTPUT.value, {"output": "001", "mode": "S"}, "@    1!Q001S\r"),
    ],
)
def test_command_payloads_and_lengths(cmd: str, kwargs: dict, expected: str) -> None:
    protocol = _prot()
    encoded = protocol.encode_command(cmd, **kwargs)
    assert encoded.decode("utf-8") == expected
    # Verify framing: starts with '@', has 5-char account and ends with CR
    assert expected.startswith("@") and expected.endswith("\r")
    assert expected[1:6] == "    1"
