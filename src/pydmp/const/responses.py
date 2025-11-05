"""DMP protocol response prefixes."""

from enum import Enum


class DMPResponse(str, Enum):
    """DMP panel response message prefixes."""

    # Status responses
    AREA_STATUS = "*WA"
    ZONE_STATUS = "*WB"
    OUTPUT_STATUS = "*WQ"
    SYSTEM_STATUS = "*WS"
    MAC_SERIAL = "*ZX1"
    SOFTWARE_VERSION = "* "

    # User management responses
    USER_CODES = "*P="
    USER_PROFILES = "*U"

    # Command acknowledgments
    ACK = "+"
    NAK = "-"
