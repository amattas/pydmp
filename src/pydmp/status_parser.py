"""Helper to convert Serial 3 (S3) messages into structured, typed events.

This module maps a low-level S3Message (from status_server) to enums and
fields from pydmp.const, making it easier to act on realtime events.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const.events import (
    DMPArmingEvent,
    DMPEquipmentEvent,
    DMPEventType,
    DMPHolidayEvent,
    DMPQualifierEvent,
    DMPRealTimeStatusEvent,
    DMPScheduleEvent,
    DMPUserCodeEvent,
    DMPZoneEvent,
)
from .const.strings import SYSTEM_MESSAGES
from .status_server import S3Message


@dataclass
class ParsedEvent:
    """Structured representation of a realtime SCS‑VR Z-message.

    Fields may be None if not applicable for the message category.
    """

    account: str
    category: DMPEventType | None
    type_code: str | None
    code_enum: object | None  # one of the DMP*Event enums above, when applicable
    area: str | None
    area_name: str | None
    zone: str | None
    zone_name: str | None
    device: str | None
    device_name: str | None
    system_code: str | None
    system_text: str | None
    fields: list[str]
    raw: str


def _get_field(fields: list[str], key: str) -> str | None:
    prefix = f"{key} "
    for f in fields:
        if f.startswith(prefix):
            return f[len(prefix) :].strip()
    return None


def _split_number_name(value: str) -> tuple[str, str | None]:
    if '"' in value:
        num, name = value.split('"', 1)
        return num.strip(), name.strip()
    return value.strip(), None


def parse_s3_message(msg: S3Message) -> ParsedEvent:
    """Convert a Serial 3 (S3) message to a structured ParsedEvent with enums.

    This function does not mutate any panel state; it only interprets the
    incoming message. Use it inside your DMPStatusServer callbacks.
    """

    # Map category
    category: DMPEventType | None
    try:
        category = DMPEventType(msg.definition)
    except ValueError:
        category = None

    # Extract common numeric/name fields
    area_raw = _get_field(msg.fields, "a")
    zone_raw = _get_field(msg.fields, "z")
    device_raw = _get_field(msg.fields, "v")
    system_code = _get_field(msg.fields, "s")

    area_num: str | None = None
    area_name: str | None = None
    zone_num: str | None = None
    zone_name: str | None = None
    device_num: str | None = None
    device_name: str | None = None

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
    system_text: str | None = None
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
