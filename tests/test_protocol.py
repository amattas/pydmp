"""Tests for DMP protocol encoding/decoding."""

import pytest

from pydmp.const.commands import DMPCommand
from pydmp.const.states import AreaState, ZoneState
from pydmp.exceptions import DMPProtocolError
from pydmp.protocol import DMPProtocol, StatusResponse


class TestDMPProtocol:
    """Test protocol encoding/decoding."""

    def test_init(self):
        """Test initialization."""
        protocol = DMPProtocol("123", "KEY")
        assert protocol.account_number == "  123"  # Left-padded
        assert protocol.remote_key == "KEY"

    def test_init_padding(self):
        """Test account number padding."""
        protocol = DMPProtocol("1", "")
        assert protocol.account_number == "    1"
        assert len(protocol.account_number) == 5

        protocol = DMPProtocol("12345", "")
        assert protocol.account_number == "12345"

    def test_encode_auth(self):
        """Test authentication command encoding."""
        protocol = DMPProtocol("1", "TESTKEY")
        encoded = protocol.encode_command(DMPCommand.AUTH.value, key="TESTKEY")
        assert encoded == b"@    1!V2TESTKEY\r"

    def test_encode_disconnect(self):
        """Test disconnect command encoding."""
        protocol = DMPProtocol("1", "")
        encoded = protocol.encode_command(DMPCommand.DISCONNECT.value)
        assert encoded == b"@    1!V0\r"

    def test_encode_arm(self):
        """Test arm command encoding."""
        protocol = DMPProtocol("1", "")
        encoded = protocol.encode_command(DMPCommand.ARM.value, area="01", bypass="N", force="N")
        assert b"@    1!C01,NN\r" == encoded

    def test_encode_bypass_zone(self):
        """Test bypass zone command encoding."""
        protocol = DMPProtocol("1", "")
        encoded = protocol.encode_command(DMPCommand.BYPASS_ZONE.value, zone="001")
        assert encoded == b"@    1!X001\r"

    def test_encode_output(self):
        """Test output command encoding."""
        protocol = DMPProtocol("1", "")
        encoded = protocol.encode_command(DMPCommand.OUTPUT.value, output="001", mode="S")
        assert encoded == b"@    1!Q001S\r"

    def test_encode_missing_parameter(self):
        """Test encoding with missing parameter."""
        protocol = DMPProtocol("1", "")
        with pytest.raises(DMPProtocolError, match="Failed to encode command"):
            protocol.encode_command(DMPCommand.ARM.value, area="01")  # Missing 'bypass' and 'force'

    def test_decode_ack(self):
        """Test ACK response decoding."""
        protocol = DMPProtocol("1", "")
        # Format: STX @ ACCT ACK CMD \r
        # Changed to !Q for output command (matching new protocol)
        response = b"\x02@    1+!Q\r"
        result = protocol.decode_response(response)
        assert result == "ACK"

    def test_decode_nak(self):
        """Test NAK response decoding."""
        protocol = DMPProtocol("1", "")
        # Format: STX @ ACCT NAK CMD \r
        response = b"\x02@    1-!O\r"
        result = protocol.decode_response(response)
        assert result == "NAK"

    def test_decode_status_area(self):
        """Test status response with area."""
        protocol = DMPProtocol("1", "")
        # Format: STX @ ACCT + ! WB [Type][Num][State][Name] \x1e - \r
        # Position: 0-6 = "@    1", 7 = "+", 8-9 = "!W", then "B" at position 10
        response = b"\x02@    1+!WBA  1DMain Floor\x1e-\r"
        result = protocol.decode_response(response)

        assert isinstance(result, StatusResponse)
        assert "1" in result.areas
        assert result.areas["1"].state == AreaState.DISARMED
        assert result.areas["1"].name == "Main Floor"

    def test_decode_status_zone(self):
        """Test status response with zone."""
        protocol = DMPProtocol("1", "")
        # Format: L[ZZZ][State][Name]
        response = b"\x02@    1+!WBL001NFront Door\x1e-\r"
        result = protocol.decode_response(response)

        assert isinstance(result, StatusResponse)
        assert "001" in result.zones
        assert result.zones["001"].state == ZoneState.NORMAL
        assert result.zones["001"].name == "Front Door"

    def test_decode_status_multiple(self):
        """Test status response with multiple items."""
        protocol = DMPProtocol("1", "")
        response = b"\x02@    1+!WBA  1DArea 1\x1eL001NFront\x1eL002OBack\x1e-\r"
        result = protocol.decode_response(response)

        assert isinstance(result, StatusResponse)
        assert len(result.areas) == 1
        assert len(result.zones) == 2
        assert result.zones["001"].state == ZoneState.NORMAL
        assert result.zones["002"].state == ZoneState.OPEN

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
