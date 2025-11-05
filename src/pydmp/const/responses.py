"""DMP protocol response prefixes and status text maps.

Includes:
- Command acknowledgments ("+"/"-")
- Convenience text mapping for common status characters seen in status replies
  (mirrors the mapping used by hass-dmp's StatusResponse).
"""

from enum import Enum
# Human-readable status strings live in const.strings (AREA_STATUS, ZONE_STATUS)


class DMPResponse(str, Enum):
    """DMP panel response message prefixes."""

    # Status responses
    AREA_STATUS = "*WA"
    ZONE_STATUS = "*WB"
    OUTPUT_STATUS = "*WQ"
    SYSTEM_STATUS = "*WS"
    KEEP_ALIVE = "*H"
    MAC_SERIAL = "*ZX1"
    SOFTWARE_VERSION = "* "

    # User management responses
    USER_CODES = "*P="
    USER_PROFILES = "*U"

    # Command acknowledgments
    ACK = "+"
    NAK = "-"


# Area status codes (from status replies A[AAA][state])
AREA_STATUS_ARMED_AWAY: str = "A"
AREA_STATUS_DISARMED: str = "D"
AREA_STATUS_ARMED_STAY: str = "S"

# Zone status codes (from status replies L[ZZZ][state])
ZONE_STATUS_NORMAL: str = "N"
ZONE_STATUS_OPEN: str = "O"
ZONE_STATUS_SHORT: str = "S"
ZONE_STATUS_BYPASSED: str = "X"
ZONE_STATUS_LOW_BATTERY: str = "L"
ZONE_STATUS_MISSING: str = "M"


# STATUS_TEXT is provided by const.strings to allow i18n later
