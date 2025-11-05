"""DMP event types and codes."""

from enum import Enum


class DMPEventType(str, Enum):
    """DMP event categories."""

    ZONE_ALARM = "Za"
    ZONE_FORCE_ALARM = "Zb"
    DEVICE_STATUS = "Zc"
    WIRELESS_LOW_BATTERY = "Zd"
    EQUIPMENT = "Ze"
    WALK_TEST_FAIL = "Zf"
    HOLIDAYS = "Zg"
    WIRELESS_ZONE_MISSING = "Zh"
    ZONE_ACCESS = "Zj"
    WALK_TEST_VERIFY = "Zk"
    SCHEDULES = "Zl"
    SERVICE_CODE = "Zm"
    ARMING_STATUS = "Zq"
    ZONE_RESTORE = "Zr"
    SYSTEM_MESSAGE = "Zs"
    ZONE_TROUBLE = "Zt"
    USER_CODES = "Zu"
    ZONE_FAULT = "Zw"
    ZONE_BYPASS = "Zx"
    ZONE_RESET = "Zy"


class DMPEvent(str, Enum):
    """DMP event codes and descriptions."""

    # Zone types
    BLANK = "BL"
    FIRE = "FI"
    BURGLARY = "BU"
    SUPERVISORY = "SV"
    PANIC = "PN"
    EMERGENCY = "EM"
    AUXILIARY_1 = "A1"
    AUXILIARY_2 = "A2"

    # Access events
    DOOR_ACCESS_GRANTED = "DA"
    DOOR_ACCESS_DENIED_ARMED = "AA"
    DOOR_ACCESS_DENIED_INVALID_AREA = "IA"
    DOOR_ACCESS_DENIED_INVALID_TIME = "IT"
    DOOR_ACCESS_DENIED_PREVIOUS = "AP"
    DOOR_ACCESS_DENIED_INVALID_CODE = "IC"
    DOOR_ACCESS_DENIED_INVALID_LEVEL = "IL"

    # Door status
    DOOR_OPEN = "DO"
    DOOR_CLOSED = "DC"
    DOOR_HELD_OPEN = "HO"
    DOOR_FORCED_OPEN = "FO"

    # Output status
    OUTPUT_ON = "ON"
    OUTPUT_OFF = "OF"
    OUTPUT_PULSE = "PL"
    OUTPUT_TEMPORAL = "TP"

    # Equipment
    EQUIPMENT_REPAIR = "RP"
    EQUIPMENT_REPLACE = "RL"
    EQUIPMENT_REMOVE = "RM"
    EQUIPMENT_ADJUST = "AJ"
    EQUIPMENT_TEST = "TS"

    # Arming
    AREA_DISARMED = "OP"
    AREA_ARMED = "CL"
    AREA_LATE_TO_ARM = "LA"

    # User codes
    USER_CODE_CHANGED = "CH"
    USER_CODE_DELETED = "DE"
    USER_CODE_ADDED = "AD"

    # Service
    SERVICE_START = "ST"
    SERVICE_STOP = "SP"
    SERVICE = "DT"

    # All areas
    ALL_AREAS_ARMED = "AC"


# System message codes
SYSTEM_MESSAGES = {
    "000": "AC Power Restored",
    "001": "Standby Battery Restored",
    "002": "Communications Line Restored",
    "003": "Panel Tamper Restored",
    "004": "Backup Communications Restored",
    "005": "Panel Ground Restored",
    "006": "System Not Armed by Scheduled Time",
    "007": "Automatic Communication Test",
    "008": "AC Power Failure",
    "009": "Low Standby Battery",
    "010": "Low Communications Signal",
    "011": "Panel Tamper",
    "012": "Backup Communications Failure",
    "013": "Panel Ground Fault",
    "014": "Non-Alarm Message Overflow",
    "015": "Ambush/Silent Alarm",
    "018": "Alarm Message Overflow",
    "023": "Local Panel Test",
    "026": "Auxiliary Fuse Trouble",
    "027": "Auxiliary Fuse Restored",
    "028": "Telephone Line 1 Fault",
    "029": "Telephone Line 1 Restore",
    "030": "Telephone Line 2 Fault",
    "031": "Telephone Line 2 Restore",
    "032": "Supervised Wireless Interference",
    "033": "Early Morning Ambush",
    "034": "Alarm Silenced",
    "035": "Alarm Bell Normal",
    "038": "Bell Circuit Trouble",
    "039": "Bell Circuit Restored",
    "040": "Fire Alarm Message Overflow",
    "041": "Panic Zone Alarm Overflow",
    "042": "Burglary Zone Alarm Overflow",
    "043": "Bell Fuse Trouble",
    "044": "Fire/Burglary Trouble Overflow",
    "045": "Abort Signal Received",
    "046": "Zone Swinger Automatically Bypassed",
    "047": "Zone Swinger Automatically Reset",
    "048": "Backup Battery Critical - Last Message Before Poweroff",
    "049": "Cancel Signal Received",
    "050": "Supervised Wireless Trouble",
    "051": "Remote Programming",
    "053": "Bell Fuse Restored",
    "054": "Unsuccessful Remote Connect",
    "071": "Time Request",
    "072": "Network Trouble",
    "073": "Network Restoral",
    "074": "Panel Tamper During Armed State",
    "077": "Unauthorized Entry",
    "078": "System Recently Armed",
    "079": "Signal During Opened Period",
    "080": "Exit Error",
    "083": "Remote Programming Complete",
    "084": "Remote Command Received",
    "086": "Local Programming",
    "087": "Transmit Failed - Messages Not Sent",
    "088": "Automatic Test - Troubled System",
    "089": "Supervised Wireless Restored",
    "091": "Services Requested",
    "092": "No Arm/Disarm Activity",
    "093": "User Activity Not Detected",
    "094": "Activity Check Enabled",
    "095": "Activity Check Disabled",
    "096": "Alarm Verified",
    "097": "Network Test OK",
    "101": "Device Missing",
    "102": "Device Restored",
    "121": "Excessive Cellular Communication",
    "122": "Cell Communication Suppressed: Excessive Data",
}
