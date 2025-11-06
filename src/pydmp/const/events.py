"""DMP event types and codes.

Derived from DMP LT-1959 "SCS‑VR Reference Guide: Panel Messages".
This file defines:
- Event categories (Zx "Event Definition" field)
- Event type codes (tXX "Event Type" field), grouped by category

Note: Some codes (e.g., AD, IN, PR) are reused across categories by the
protocol. To avoid ambiguity in Python Enums, category-specific enums are
provided below. The legacy DMPEvent enum remains for common codes but is
not exhaustive. Prefer category enums for precise handling.
"""

from enum import Enum


class DMPEventType(str, Enum):
    """Event Definition categories (Zx)."""

    ZONE_ALARM = "Za"
    ZONE_FORCE_ARM = "Zb"
    REAL_TIME_STATUS = "Zc"  # Entré/real-time status
    WIRELESS_LOW_BATTERY = "Zd"
    EQUIPMENT = "Ze"
    ZONE_FAIL = "Zf"
    HOLIDAYS = "Zg"
    WIRELESS_ZONE_MISSING = "Zh"
    ZONE_TAMPER = "Zi"
    DOOR_ACCESS = "Zj"
    WALK_TEST_VERIFY = "Zk"
    SCHEDULES = "Zl"
    SERVICE_CODE = "Zm"
    ZONE_TRIP_COUNT = "Zp"
    ARMING_STATUS = "Zq"
    ZONE_RESTORE = "Zr"
    SYSTEM_MESSAGE = "Zs"
    ZONE_TROUBLE = "Zt"
    USER_CODES = "Zu"
    ZONE_FAULT = "Zw"
    ZONE_BYPASS = "Zx"
    ZONE_RESET = "Zy"
    RESERVED = "Zz"


class DMPEvent(str, Enum):
    """Common event type codes (legacy/unscoped).

    Prefer the category-specific enums below for full coverage and to avoid
    ambiguity where the same code is reused across categories.
    """

    # Zone types
    BLANK = "BL"
    FIRE = "FI"
    BURGLARY = "BU"
    SUPERVISORY = "SV"
    PANIC = "PN"
    EMERGENCY = "EM"
    AUXILIARY_1 = "A1"
    AUXILIARY_2 = "A2"
    CARBON_MONOXIDE = "CO"
    VIDEO_ALARM = "VA"

    # Access events (subset)
    DOOR_ACCESS_GRANTED = "DA"
    DOOR_ACCESS_DENIED_ARMED = "AA"
    DOOR_ACCESS_DENIED_INVALID_AREA = "IA"
    DOOR_ACCESS_DENIED_INVALID_TIME = "IT"
    DOOR_ACCESS_DENIED_PREVIOUS = "AP"
    DOOR_ACCESS_DENIED_INVALID_CODE = "IC"
    DOOR_ACCESS_DENIED_INVALID_LEVEL = "IL"
    DOOR_ACCESS_DENIED_WRONG_PIN = "WP"

    # Real-time status (door/output)
    DOOR_OPEN = "DO"
    DOOR_CLOSED = "DC"
    DOOR_HELD_OPEN = "HO"
    DOOR_FORCED_OPEN = "FO"
    OUTPUT_ON = "ON"
    OUTPUT_OFF = "OF"
    OUTPUT_PULSE = "PL"
    OUTPUT_TEMPORAL = "TP"
    OUTPUT_MOMENTARY = "MO"

    # Equipment (subset)
    EQUIPMENT_REPAIR = "RP"
    EQUIPMENT_REPLACE = "RL"
    EQUIPMENT_REMOVE = "RM"
    EQUIPMENT_ADJUST = "AJ"
    EQUIPMENT_TEST = "TS"

    # Arming
    AREA_DISARMED = "OP"
    AREA_ARMED = "CL"
    AREA_LATE_TO_ARM = "LA"

    # User codes (subset)
    USER_CODE_CHANGED = "CH"
    USER_CODE_DELETED = "DE"
    USER_CODE_ADDED = "AD"

    # Service / Qualifiers (subset)
    SERVICE_START = "ST"
    SERVICE_STOP = "SP"
    SERVICE = "DT"
    ALL_AREAS_ARMED = "AC"
    LOCAL_ALARM_OR_RESTORE = "LC"


# Category‑specific event type codes (tXX)


class DMPZoneEvent(str, Enum):
    BLANK = "BL"
    FIRE = "FI"
    BURGLARY = "BU"
    SUPERVISORY = "SV"
    PANIC = "PN"
    EMERGENCY = "EM"
    AUXILIARY_1 = "A1"
    AUXILIARY_2 = "A2"
    CARBON_MONOXIDE = "CO"
    VIDEO_ALARM = "VA"


class DMPScheduleEvent(str, Enum):
    PERMANENT = "PE"
    TEMPORARY = "TE"
    PRIMARY = "PR"
    SECONDARY = "SE"
    SHIFT_ONE = "S1"
    SHIFT_TWO = "S2"
    SHIFT_THREE = "S3"
    SHIFT_FOUR = "S4"


class DMPHolidayEvent(str, Enum):
    HOLIDAY_A = "HA"
    HOLIDAY_B = "HB"
    HOLIDAY_C = "HC"


class DMPUserCodeEvent(str, Enum):
    ADDED = "AD"
    CHANGED = "CH"
    DELETED = "DE"
    INACTIVE = "IN"


class DMPArmingEvent(str, Enum):
    DISARMED = "OP"
    ARMED = "CL"
    LATE_TO_ARM = "LA"


class DMPAccessEvent(str, Enum):
    ACCESS_GRANTED = "DA"
    DENIED_ARMED = "AA"
    DENIED_INVALID_AREA = "IA"
    DENIED_INVALID_TIME = "IT"
    DENIED_PREVIOUS = "AP"
    DENIED_INVALID_CODE = "IC"
    DENIED_INVALID_LEVEL = "IL"
    DENIED_WRONG_PIN = "WP"
    DENIED_INACTIVE_USER = "IN"


class DMPRealTimeStatusEvent(str, Enum):
    DOOR_OPEN = "DO"
    DOOR_CLOSED = "DC"
    DOOR_HELD_OPEN = "HO"
    DOOR_FORCED_OPEN = "FO"
    OUTPUT_ON = "ON"
    OUTPUT_OFF = "OF"
    OUTPUT_PULSE = "PL"
    OUTPUT_TEMPORAL = "TP"
    OUTPUT_MOMENTARY = "MO"


class DMPEquipmentEvent(str, Enum):
    REPAIR = "RP"
    REPLACE = "RL"
    ADD = "AD"
    REMOVE = "RM"
    ADJUST = "AJ"
    TEST = "TS"
    SYSTEM_OPTIONS_EEPROM = "SO"
    PRINTER_EEPROM = "PR"
    LINE_CARD_EEPROM = "LC"
    HOST_PORT_1_EEPROM = "H1"
    HOST_PORT_2_EEPROM = "H2"
    SERIAL_PORT_EEPROM = "SP"
    LOG = "LG"
    ENTIRE_EEPROM = "EE"
    CONTACT_ID = "CD"


class DMPServiceUserEvent(str, Enum):
    START = "ST"
    STOP = "SP"


class DMPQualifierEvent(str, Enum):
    SERVICE = "DT"
    ALL_AREAS_ARMED = "AC"
    LOCAL_ALARM_OR_RESTORE = "LC"
