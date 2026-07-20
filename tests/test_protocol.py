"""Tests for DMP protocol encoding/decoding."""

import pytest

from pydmp.const.commands import DMPCommand
from pydmp.exceptions import DMPProtocolError
from pydmp.protocol import DMPProtocol, StatusResponse


class TestDMPProtocol:
    """Test protocol encoding/decoding."""

    @pytest.mark.parametrize(
        "account,expected",
        [
            ("123", "  123"),
            ("1", "    1"),
            ("12345", "12345"),
        ],
    )
    def test_init(self, account, expected):
        """Test initialization and account number padding."""
        protocol = DMPProtocol(account, "KEY")
        assert protocol.account_number == expected
        assert len(protocol.account_number) == 5
        assert protocol.remote_key == "KEY"

    def test_encode_missing_parameter(self):
        """Test encoding with missing parameter."""
        protocol = DMPProtocol("1", "")
        with pytest.raises(DMPProtocolError, match="Failed to encode command"):
            protocol.encode_command(DMPCommand.ARM.value, area="01")  # Missing 'bypass' and 'force'

    @pytest.mark.parametrize(
        "response,expected",
        [
            # Format: STX @ ACCT ACK CMD \r
            (b"\x02@    1+!Q\r", "ACK"),
            # Format: STX @ ACCT NAK CMD \r
            (b"\x02@    1-!O\r", "NAK"),
        ],
    )
    def test_decode_ack_nak(self, response, expected):
        """Test ACK/NAK response decoding."""
        protocol = DMPProtocol("1", "")
        result = protocol.decode_response(response)
        assert result == expected

    @pytest.mark.parametrize(
        "response,expected",
        [
            (
                # Format: STX @ ACCT + ! WB [Type][Num][State][Name] \x1e - \r
                b"\x02@    1+!WBA  1DMain Floor\x1e-\r",
                {"areas": {"1": {"state": "D", "name": "Main Floor"}}, "zones": {}},
            ),
            (
                # Format: L[ZZZ][State][Name]
                b"\x02@    1+!WBL001NFront Door\x1e-\r",
                {"areas": {}, "zones": {"001": {"state": "N", "name": "Front Door"}}},
            ),
            (
                # Panel uses '*WB' prefix (observed on wire)
                b"\x02@    1*WBL002OLiving Room Window\x1e-\r",
                {"areas": {}, "zones": {"002": {"state": "O", "name": "Living Room Window"}}},
            ),
            (
                b"\x02@    1+!WBA  1DArea 1\x1eL001NFront\x1eL002OBack\x1e-\r",
                {
                    "areas": {"1": {"state": "D", "name": "Area 1"}},
                    "zones": {"001": {"state": "N", "name": "Front"}, "002": {"state": "O", "name": "Back"}},
                },
            ),
        ],
    )
    def test_decode_status(self, response, expected):
        """Test status response decoding for areas and zones."""
        protocol = DMPProtocol("1", "")
        result = protocol.decode_response(response)

        assert isinstance(result, StatusResponse)
        assert len(result.areas) == len(expected["areas"])
        assert len(result.zones) == len(expected["zones"])
        for num, fields in expected["areas"].items():
            assert num in result.areas
            assert result.areas[num].state == fields["state"]
            assert result.areas[num].name == fields["name"]
        for num, fields in expected["zones"].items():
            assert num in result.zones
            assert result.zones[num].state == fields["state"]
            assert result.zones[num].name == fields["name"]

    def test_decode_empty_response(self):
        """Test empty response."""
        protocol = DMPProtocol("1", "")
        result = protocol.decode_response(b"")
        assert result is None

    def test_decode_auth_response(self):
        """Test authentication response (typically empty/None)."""
        protocol = DMPProtocol("1", "")
        response = b"\x02@    1!V2\r"
        result = protocol.decode_response(response)
        assert result is None  # Auth doesn't return specific data
