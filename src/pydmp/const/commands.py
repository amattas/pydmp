"""DMP protocol commands."""

from enum import Enum


class DMPCommand(str, Enum):
    """DMP panel commands."""

    # Authentication
    AUTH = "!V2{key}"
    DISCONNECT = "!V0"

    # Keep alive
    KEEP_ALIVE = "!H"

    # System information
    GET_MAC = "?ZX1"
    GET_SOFTWARE_VERSION = "? "
    GET_SYSTEM_STATUS = "?WS"

    # User management
    GET_USER_CODES = "?P={user}"  # Format: ?P=0000 for all, ?P=0001 for user 1
    GET_USER_PROFILES = "?U{profile}"  # Format: ?U000 for all, ?U001 for profile 1

    # Status queries
    GET_AREA_STATUS = "?WA{area}"  # Format: ?WA01 for area 1, ?WA for continuation
    GET_AREA_STATUS_CONT = "?WA"    # Continuation (no params)
    GET_OUTPUT_STATUS = "?WQ{output}"  # Format: ?WQ001 for output 1, ?WQ for continuation
    GET_OUTPUT_STATUS_CONT = "?WQ"     # Continuation (no params)
    GET_ZONE_STATUS = "?WB**Y{zone}"  # Format: ?WB**Y001 for initial query
    GET_ZONE_STATUS_CONT = "?WB"      # Continuation (no params)

    # Area control
    ARM = "!C{area},{bypass}{force}"
    DISARM = "!O{area}"

    # Zone control
    BYPASS_ZONE = "!X{zone}"
    RESTORE_ZONE = "!Y{zone}"
    SENSOR_RESET = "!E001"

    # Output control
    OUTPUT = "!Q{output}{mode}"


# Protocol constants
DEFAULT_PORT = 2011
RATE_LIMIT_SECONDS = 0.3
MESSAGE_TERMINATOR = "\r"
MESSAGE_PREFIX = "@"
RESPONSE_DELIMITER = "\x02"
ZONE_DELIMITER = "\x1e"
