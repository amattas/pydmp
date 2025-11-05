"""State definitions for DMP entities."""

from enum import Enum


class AreaState(str, Enum):
    """Area arming states."""

    DISARMED = "D"
    ARMED_AWAY = "A"
    ARMED_STAY = "S"
    ARMED_NIGHT = "N"
    ARMED_INSTANT = "I"
    ARMING = "arming"
    DISARMING = "disarming"
    UNKNOWN = "unknown"


class ZoneState(str, Enum):
    """Zone states."""

    NORMAL = "N"
    OPEN = "O"
    SHORT = "S"
    BYPASSED = "X"
    LOW_BATTERY = "L"
    MISSING = "M"
    ALARM = "alarm"
    FAULT = "fault"
    UNKNOWN = "unknown"


class ZoneType(str, Enum):
    """Zone types from DMP."""

    BLANK = "BL"
    FIRE = "FI"
    BURGLARY = "BU"
    SUPERVISORY = "SV"
    PANIC = "PN"
    EMERGENCY = "EM"
    AUXILIARY_1 = "A1"
    AUXILIARY_2 = "A2"
    DOOR = "door"
    WINDOW = "window"
    MOTION = "motion"
    GLASS_BREAK = "glass"
    SMOKE = "smoke"
    CO = "co"
    UNKNOWN = "unknown"


class OutputState(str, Enum):
    """Output states."""

    OFF = "OF"
    ON = "ON"
    PULSE = "PL"
    TEMPORAL = "TP"
    UNKNOWN = "unknown"
