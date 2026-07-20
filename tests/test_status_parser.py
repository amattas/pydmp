from collections.abc import Callable

import pytest

from pydmp.const import (
    DMPEquipmentEvent,
    DMPEventType,
    DMPHolidayEvent,
    DMPQualifierEvent,
    DMPRealTimeStatusEvent,
    DMPScheduleEvent,
    DMPUserCodeEvent,
    DMPZoneEvent,
)
from pydmp.status_parser import parse_s3_message
from pydmp.status_server import S3Message


def _msg(defn: str, type_code: str | None, fields: list[str]):
    return S3Message(account="00001", definition=defn, type_code=type_code, fields=fields, raw="")


def _check_zone_alarm(evt):
    assert isinstance(evt.code_enum, DMPZoneEvent)
    assert evt.zone == "001"
    assert evt.zone_name == "Front"


def _check_user_code(evt):
    assert isinstance(evt.code_enum, DMPUserCodeEvent)


def _check_schedule(evt):
    assert isinstance(evt.code_enum, DMPScheduleEvent)


def _check_holiday(evt):
    assert isinstance(evt.code_enum, DMPHolidayEvent)


def _check_equipment(evt):
    assert isinstance(evt.code_enum, DMPEquipmentEvent)


def _check_qualifier_fallback(evt):
    assert isinstance(evt.code_enum, DMPQualifierEvent | type(None))


def _check_real_time_status(evt):
    assert isinstance(evt.code_enum, DMPRealTimeStatusEvent)
    assert evt.device == "002"
    assert evt.device_name == "OUT2"


def _check_system_message(evt):
    assert evt.system_code == "072"
    assert isinstance(evt.system_text, str | type(None))


def _check_no_typecode(evt):
    assert evt.type_code is None


PARSE_CASES: list[tuple[str, S3Message, DMPEventType | None, Callable | None]] = [
    (
        "zone-alarm",
        _msg("Za", "BU", ["Za", 't "BU', 'z 001"Front']),
        DMPEventType.ZONE_ALARM,
        _check_zone_alarm,
    ),
    (
        "user-code",
        _msg("Zu", "AD", ["Zu", 't "AD', 'u 0123"USER']),
        DMPEventType.USER_CODES,
        _check_user_code,
    ),
    (
        "schedule",
        _msg("Zl", "PE", ["Zl", 't "PE']),
        DMPEventType.SCHEDULES,
        _check_schedule,
    ),
    (
        "holiday",
        _msg("Zg", "HA", ["Zg", 't "HA']),
        DMPEventType.HOLIDAYS,
        _check_holiday,
    ),
    (
        "equipment",
        _msg("Ze", "RP", ["Ze", 't "RP']),
        DMPEventType.EQUIPMENT,
        _check_equipment,
    ),
    (
        "qualifier-fallback",
        _msg("Za", "AC", ["Za", 't "AC']),
        None,
        _check_qualifier_fallback,
    ),
    (
        "real-time-status",
        S3Message(
            account="00001",
            definition="Zc",
            type_code="ON",
            fields=["Zc", "060", 't "ON', 'v 002"OUT2'],
            raw="",
        ),
        DMPEventType.REAL_TIME_STATUS,
        _check_real_time_status,
    ),
    (
        "system-message",
        _msg("Zs", None, ["Zs", "s 072"]),
        DMPEventType.SYSTEM_MESSAGE,
        _check_system_message,
    ),
    (
        "z-body-no-typecode",
        None,
        None,
        _check_no_typecode,
    ),
]


@pytest.mark.parametrize(
    ("_id", "msg", "expected_category", "extra_checks"),
    PARSE_CASES,
    ids=[c[0] for c in PARSE_CASES],
)
def test_parse_s3_message(_id, msg, expected_category, extra_checks):
    if _id == "z-body-no-typecode":
        from pydmp.status_server import DMPStatusServer

        msg = DMPStatusServer._parse_z_body("00001", "Za\\060\\foo\\bar")
        assert msg.definition.startswith("Za")
        extra_checks(msg)
        return

    evt = parse_s3_message(msg)
    if expected_category is not None:
        assert evt.category == expected_category
    if extra_checks is not None:
        extra_checks(evt)
