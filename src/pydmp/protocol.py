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


@dataclass
class UserCode:
    """Decrypted user code record."""

    number: str
    code: str
    pin: str
    profiles: tuple[str, str, str, str]
    temp_date: str
    exp_date: str
    name: str


@dataclass
class UserCodesResponse:
    users: list[UserCode]
    has_more: bool
    last_number: str | None


@dataclass
class UserProfile:
    """User profile record (not encrypted)."""

    number: str
    areas_mask: str
    access_areas_mask: str
    output_group: str
    menu_options: str
    rearm_delay: str
    name: str


@dataclass
class UserProfilesResponse:
    profiles: list[UserProfile]
    has_more: bool
    last_number: str | None


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

    def decode_response(self, response: bytes) -> str | StatusResponse | UserCodesResponse | UserProfilesResponse | None:
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
            decoded = response.decode("utf-8", errors="replace")
            _LOGGER.debug(f"Decoding response stream ({len(decoded)} chars)")

            # Split by response delimiter (STX)
            lines = decoded.split(RESPONSE_DELIMITER)
            for i, line in enumerate(lines):
                if not line:
                    continue
                _LOGGER.debug(f"[resp line {i}] {line[:120]!r}")

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

                # Status response (*WB, !WB, or ?WB)
                # Panels may prefix status frames with '*', e.g. "@    1*WBL001N..."
                # Others return acknowledgements with '!WB' or queries with '?WB'.
                # Find the first occurrence of any marker then parse the payload
                # immediately following that 3-char marker.
                marker_pos = -1
                for marker in ("*WB", "!WB", "?WB"):
                    pos = line.find(marker)
                    if pos != -1:
                        marker_pos = pos
                        break
                if marker_pos != -1 and len(line) > marker_pos + 3:
                    start = marker_pos + 3
                    self._parse_status_line(line[start:], status_response)
                    has_status_data = True

                # User codes (*P=...)
                if "*P=" in line:
                    return self._parse_user_codes_line(line.split("*P=", 1)[1])

                # User profiles (*U...)
                if "*U" in line:
                    return self._parse_user_profiles_line(line.split("*U", 1)[1])

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

    def _parse_user_codes_line(self, data: str) -> UserCodesResponse:
        """Parse user codes response, decrypting entries.

        Data is a sequence of encrypted user strings delimited by ZONE_DELIMITER.
        """
        users: list[UserCode] = []
        has_more = False
        last_number: str | None = None

        for item in data.split(ZONE_DELIMITER):
            item = item.rstrip("\r")
            if not item:
                continue
            if item.startswith("----"):
                has_more = True
                continue
            # Decrypt with LFSR
            plain = self.crypto.decrypt_string(item)
            if len(plain) < 44:
                continue
            num = plain[0:4]
            code = plain[4:16].split("F", 1)[0]
            pin = plain[16:22].split("F", 1)[0]
            p1 = plain[22:25]
            p2 = plain[25:28]
            p3 = plain[28:31]
            p4 = plain[31:34]
            temp = plain[34:40]
            exp = plain[40:44]
            name = plain[44:]
            last_number = num
            users.append(
                UserCode(
                    number=num,
                    code=code,
                    pin=pin,
                    profiles=(p1, p2, p3, p4),
                    temp_date=temp,
                    exp_date=exp,
                    name=name,
                )
            )
        return UserCodesResponse(users=users, has_more=has_more, last_number=last_number)

    def _parse_user_profiles_line(self, data: str) -> UserProfilesResponse:
        """Parse user profiles response (*U...)."""
        profiles: list[UserProfile] = []
        has_more = False
        last_number: str | None = None

        for item in data.split(ZONE_DELIMITER):
            item = item.rstrip("\r")
            if not item:
                continue
            if item.startswith("----"):
                has_more = True
                continue
            # Fields per lua slicing
            num = item[0:3]
            areas = item[3:11]
            acc_areas = item[11:19]
            out_grp = item[19:22]
            menu = item[22:30]
            # Optional indexes
            rearm = item[46:49] if len(item) >= 49 else ""
            name = item[49:] if len(item) >= 49 else item[30:]
            last_number = num
            profiles.append(
                UserProfile(
                    number=num,
                    areas_mask=areas,
                    access_areas_mask=acc_areas,
                    output_group=out_grp,
                    menu_options=menu,
                    rearm_delay=rearm,
                    name=name,
                )
            )
        return UserProfilesResponse(profiles=profiles, has_more=has_more, last_number=last_number)
