"""Helper to convert SCS‑VR messages into structured, typed events.

This module maps a low-level SCSVRMessage (from status_server) to enums and
fields from pydmp.const, making it easier to act on realtime events.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .status_server import S3Message
from .const.events import (
    DMPEventType,
    DMPArmingEvent,
    DMPRealTimeStatusEvent,
    DMPZoneEvent,
    DMPUserCodeEvent,
    DMPScheduleEvent,
    DMPHolidayEvent,
    DMPEquipmentEvent,
    DMPQualifierEvent,
)
from .const.strings import SYSTEM_MESSAGES


@dataclass
class ParsedEvent:
    """Structured representation of a realtime SCS‑VR Z-message.

    Fields may be None if not applicable for the message category.
    """

    account: str
    category: Optional[DMPEventType]
    type_code: Optional[str]
    code_enum: object | None  # one of the DMP*Event enums above, when applicable
    area: Optional[str]
    area_name: Optional[str]
    zone: Optional[str]
    zone_name: Optional[str]
    device: Optional[str]
    device_name: Optional[str]
    system_code: Optional[str]
    system_text: Optional[str]
    fields: list[str]
    raw: str


def _get_field(fields: list[str], key: str) -> Optional[str]:
    prefix = f"{key} "
    for f in fields:
        if f.startswith(prefix):
            return f[len(prefix) :].strip()
    return None


def _split_number_name(value: str) -> Tuple[str, Optional[str]]:
    if '"' in value:
        num, name = value.split('"', 1)
        return num.strip(), name.strip()
    return value.strip(), None


def parse_scsvr_message(msg: S3Message) -> ParsedEvent:
    """Convert SCSVRMessage to a structured ParsedEvent with enums.

    This function does not mutate any panel state; it only interprets the
    incoming message. Use it inside your DMPStatusServer callbacks.
    """

    # Map category
    category: Optional[DMPEventType]
    try:
        category = DMPEventType(msg.definition)
    except ValueError:
        category = None

    # Extract common numeric/name fields
    area_raw = _get_field(msg.fields, "a")
    zone_raw = _get_field(msg.fields, "z")
    device_raw = _get_field(msg.fields, "v")
    system_code = _get_field(msg.fields, "s")

    area_num: Optional[str] = None
    area_name: Optional[str] = None
    zone_num: Optional[str] = None
    zone_name: Optional[str] = None
    device_num: Optional[str] = None
    device_name: Optional[str] = None

    if area_raw is not None:
        area_num, area_name = _split_number_name(area_raw)
    if zone_raw is not None:
        zone_num, zone_name = _split_number_name(zone_raw)
    if device_raw is not None:
        device_num, device_name = _split_number_name(device_raw)

    # Map type_code into a specific enum when applicable
    code_enum: object | None = None
    if category is not None and msg.type_code:
        code = msg.type_code
        try:
            if category is DMPEventType.ARMING_STATUS:
                code_enum = DMPArmingEvent(code)
            elif category is DMPEventType.REAL_TIME_STATUS:
                code_enum = DMPRealTimeStatusEvent(code)
            elif category in (
                DMPEventType.ZONE_ALARM,
                DMPEventType.ZONE_RESTORE,
                DMPEventType.ZONE_TROUBLE,
                DMPEventType.ZONE_FAULT,
                DMPEventType.ZONE_BYPASS,
                DMPEventType.ZONE_RESET,
            ):
                code_enum = DMPZoneEvent(code)
            elif category is DMPEventType.USER_CODES:
                code_enum = DMPUserCodeEvent(code)
            elif category is DMPEventType.SCHEDULES:
                code_enum = DMPScheduleEvent(code)
            elif category is DMPEventType.HOLIDAYS:
                code_enum = DMPHolidayEvent(code)
            elif category is DMPEventType.EQUIPMENT:
                code_enum = DMPEquipmentEvent(code)
            else:
                # Qualifiers sometimes ride along in other frames
                try:
                    code_enum = DMPQualifierEvent(code)
                except ValueError:
                    code_enum = None
        except ValueError:
            code_enum = None

    # System message text (Zs)
    system_text: Optional[str] = None
    if category is DMPEventType.SYSTEM_MESSAGE and system_code:
        system_text = SYSTEM_MESSAGES.get(system_code)

    return ParsedEvent(
        account=msg.account,
        category=category,
        type_code=msg.type_code,
        code_enum=code_enum,
        area=area_num,
        area_name=area_name,
        zone=zone_num,
        zone_name=zone_name,
        device=device_num,
        device_name=device_name,
        system_code=system_code,
        system_text=system_text,
        fields=msg.fields,
        raw=msg.raw,
    )
