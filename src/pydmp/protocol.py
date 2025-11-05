"""DMP protocol encoder and decoder."""

import logging
from dataclasses import dataclass
from typing import Any

from .const.protocol import (
    MESSAGE_PREFIX,
    MESSAGE_TERMINATOR,
    RESPONSE_DELIMITER,
    ZONE_DELIMITER,
)
from .const.responses import (
    DMPResponse,
    AREA_STATUS_ARMED_AWAY,
    AREA_STATUS_DISARMED,
    AREA_STATUS_ARMED_STAY,
    ZONE_STATUS_NORMAL,
    ZONE_STATUS_OPEN,
    ZONE_STATUS_SHORT,
    ZONE_STATUS_BYPASSED,
    ZONE_STATUS_LOW_BATTERY,
    ZONE_STATUS_MISSING,
)
from .crypto import DMPCrypto
from .exceptions import DMPInvalidResponseError, DMPProtocolError

_LOGGER = logging.getLogger(__name__)


@dataclass
class AreaStatus:
    """Area status from panel."""

    number: str
    state: str  # 'A','D','S' (or 'unknown')
    name: str


@dataclass
class ZoneStatus:
    """Zone status from panel."""

    number: str
    state: str  # 'N','O','S','X','L','M' (or 'unknown')
    name: str


@dataclass
class StatusResponse:
    """Combined status response from panel."""

    areas: dict[str, AreaStatus]
    zones: dict[str, ZoneStatus]


class DMPProtocol:
    """DMP protocol encoder/decoder."""

    def __init__(self, account_number: str, remote_key: str = ""):
        """Initialize protocol handler.

        Args:
            account_number: 5-digit account number (left-padded with spaces or zeros)
            remote_key: Remote key for authentication
        """
        # Ensure account is 5 characters, left-pad with spaces
        self.account_number = account_number.rjust(5)
        if len(self.account_number) != 5:
            raise ValueError("Account number must be 5 digits or less")

        self.remote_key = remote_key

        # Convert account to int for crypto (strip spaces/leading zeros)
        account_int = int(self.account_number.strip() or "0")
        self.crypto = DMPCrypto(account_int, remote_key)

        _LOGGER.debug(f"Protocol initialized for account: {self.account_number}")

    def encode_command(
        self,
        command: str,
        **kwargs: Any,
    ) -> bytes:
        """Encode a command for transmission to panel.

        Args:
            command: Command template (e.g., "!C{area},{bypass}{force}")
            **kwargs: Parameters to substitute into command template

        Returns:
            Encoded command as bytes

        Raises:
            DMPProtocolError: If command cannot be encoded
        """
        try:
            # Format command with parameters
            formatted_command = command.format(**kwargs)

            # Build full message: @[ACCOUNT][COMMAND]\r
            message = f"{MESSAGE_PREFIX}{self.account_number}{formatted_command}{MESSAGE_TERMINATOR}"

            _LOGGER.debug(f"Encoded command: {message.strip()}")
            return message.encode()

        except (KeyError, ValueError) as e:
            raise DMPProtocolError(f"Failed to encode command: {e}") from e

    def decode_response(self, response: bytes) -> str | StatusResponse | None:
        """Decode response from panel.

        Args:
            response: Raw bytes from panel

        Returns:
            - ACK/NAK string for command acknowledgments
            - StatusResponse for status queries
            - None for empty/auth responses

        Raises:
            DMPInvalidResponseError: If response cannot be decoded
        """
        if not response:
            return None

        try:
            decoded = response.decode("utf-8")
            _LOGGER.debug(f"Decoding response: {decoded[:100]}...")

            # Split by response delimiter (STX)
            lines = decoded.split(RESPONSE_DELIMITER)

            status_response = StatusResponse(areas={}, zones={})
            has_status_data = False

            for line in lines:
                if not line or len(line) < 8:
                    continue

                # Response format: "@    1+!C\r" where:
                # 0-5 = "@    1" (account with prefix)
                # 6 = '+' (ACK) or '-' (NAK)
                # 7-8 = "!C" (command)

                # ACK/NAK character is at position 6
                ack_nak_char = line[6:7] if len(line) > 6 else ""

                # Command starts at position 7
                cmd_with_prefix = line[7:9] if len(line) > 8 else ""

                # Authentication/disconnect response (!V)
                if cmd_with_prefix == "!V":
                    continue

                # Command acknowledgment for arm/disarm/bypass/output
                # These have ! followed by C/O/X/Y/Q
                if len(cmd_with_prefix) == 2 and cmd_with_prefix[0] == "!" and cmd_with_prefix[1] in ["C", "O", "X", "Y", "Q"]:
                    if ack_nak_char == DMPResponse.ACK.value:
                        return "ACK"
                    elif ack_nak_char == DMPResponse.NAK.value:
                        return "NAK"

                # Status response (?WB or !WB)
                # Status query responses: "@    1+!WB..." or "@    1+?WB..."
                if len(line) > 9 and line[7:10] in ["!WB", "?WB"]:
                    self._parse_status_line(line[10:], status_response)
                    has_status_data = True

            if has_status_data:
                return status_response

            return None

        except (UnicodeDecodeError, IndexError) as e:
            raise DMPInvalidResponseError(f"Failed to decode response: {e}") from e

    def _parse_status_line(self, status_data: str, response: StatusResponse) -> None:
        """Parse a status line and populate response object.

        Args:
            status_data: Status data portion of response
            response: StatusResponse object to populate
        """
        # Status data format: [Type][Number][State][Name]\x1e...
        # Type: 'A' = Area, 'L' = Zone (Line)
        # Area: A[X][State][Name] where X is 1-8
        # Zone: L[XXX][State][Name] where XXX is 001-999

        if not status_data or status_data.startswith("-\r"):
            return

        # Split by zone delimiter
        items = status_data.split(ZONE_DELIMITER)

        for item in items:
            if len(item) < 5:
                continue

            item_type = item[0:1]
            if item_type == "A":
                # Area: A[X][State][Name]
                number = item[1:4]  # Get 3 chars, strip leading zeros/spaces later
                state_char = item[4:5]
                name = item[5:].strip()

                # Parse area number (positions 1-3, usually ' 1', ' 2', etc.)
                area_num = number.strip()
                if not area_num:
                    continue

                # Use raw area state character
                if state_char in (
                    AREA_STATUS_ARMED_AWAY,
                    AREA_STATUS_DISARMED,
                    AREA_STATUS_ARMED_STAY,
                ):
                    state = state_char
                else:
                    state = "unknown"

                response.areas[area_num] = AreaStatus(
                    number=area_num, state=state, name=name
                )

            elif item_type == "L":
                # Zone: L[XXX][State][Name]
                number = item[1:4]
                state_char = item[4:5]
                name = item[5:].strip()

                # Use raw zone state character
                if state_char in (
                    ZONE_STATUS_NORMAL,
                    ZONE_STATUS_OPEN,
                    ZONE_STATUS_SHORT,
                    ZONE_STATUS_BYPASSED,
                    ZONE_STATUS_LOW_BATTERY,
                    ZONE_STATUS_MISSING,
                ):
                    state = state_char
                else:
                    state = "unknown"

                response.zones[number] = ZoneStatus(number=number, state=state, name=name)

        _LOGGER.debug(f"Parsed status: {len(response.areas)} areas, {len(response.zones)} zones")
