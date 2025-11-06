"""Human‑readable strings for statuses and system messages.

This module centralizes user‑facing strings to make future
internationalization (i18n) straightforward. By default, it
exposes English strings. A future enhancement could expose
per‑locale mappings and a simple selection mechanism.
"""

# Status text, split by entity to avoid ambiguity (e.g., 'S')

# Areas: A/D/S
AREA_STATUS: dict[str, str] = {
    "A": "Armed (Away)",
    "D": "Disarmed",
    "S": "Armed (Stay)",
}

# Zones: N/O/S/X/L/M
ZONE_STATUS: dict[str, str] = {
    "N": "Normal",
    "O": "Open",
    "S": "Short",
    "X": "Bypassed",
    "L": "Low Battery",
    "M": "Missing",
}


# Outputs: ON/OF/PL/TP/MO (derived from *WQ and realtime)
OUTPUT_STATUS: dict[str, str] = {
    "ON": "On",
    "OF": "Off",
    "PL": "Pulse",
    "TP": "Temporal",
    "MO": "Momentary/Wink",
}


# System message codes (subset per LT-1959)
SYSTEM_MESSAGES: dict[str, str] = {
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
