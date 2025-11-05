"""DMP protocol response prefixes and status text maps.

Includes:
- Command acknowledgments ("+"/"-")
- Convenience text mapping for common status characters seen in status replies
  (mirrors the mapping used by hass-dmp's StatusResponse).
"""

from enum import Enum
from .strings import STATUS_TEXT as STATUS_TEXT  # re-export for convenience


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


# STATUS_TEXT is provided by const.strings to allow i18n later
