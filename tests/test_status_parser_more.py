from pydmp.status_parser import parse_s3_message
from pydmp.status_server import S3Message
from pydmp.const import (
    DMPEventType,
    DMPZoneEvent,
    DMPUserCodeEvent,
    DMPScheduleEvent,
    DMPHolidayEvent,
    DMPEquipmentEvent,
    DMPQualifierEvent,
)


def _msg(defn: str, type_code: str | None, fields: list[str]):
    return S3Message(account="00001", definition=defn, type_code=type_code, fields=fields, raw="")


def test_parse_zone_alarm_and_user_code():
    m = _msg("Za", "BU", ["Za", 't "BU', 'z 001"Front'])
    evt = parse_s3_message(m)
    assert evt.category == DMPEventType.ZONE_ALARM
    assert isinstance(evt.code_enum, DMPZoneEvent)
    assert evt.zone == "001"
    assert evt.zone_name == "Front"

    m2 = _msg("Zu", "AD", ["Zu", 't "AD', 'u 0123"USER'])
    evt2 = parse_s3_message(m2)
    assert evt2.category == DMPEventType.USER_CODES
    assert isinstance(evt2.code_enum, DMPUserCodeEvent)


def test_parse_schedules_holidays_equipment_and_qualifier():
    m = _msg("Zl", "PE", ["Zl", 't "PE'])
    evt = parse_s3_message(m)
    assert evt.category == DMPEventType.SCHEDULES
    assert isinstance(evt.code_enum, DMPScheduleEvent)

    mh = _msg("Zg", "HA", ["Zg", 't "HA'])
    evth = parse_s3_message(mh)
    assert evth.category == DMPEventType.HOLIDAYS
    assert isinstance(evth.code_enum, DMPHolidayEvent)

    me = _msg("Ze", "RP", ["Ze", 't "RP'])
    evte = parse_s3_message(me)
    assert evte.category == DMPEventType.EQUIPMENT
    assert isinstance(evte.code_enum, DMPEquipmentEvent)

    mq = _msg("Za", "AC", ["Za", 't "AC'])  # Qualifier fallback
    evtq = parse_s3_message(mq)
    assert isinstance(evtq.code_enum, (DMPQualifierEvent, type(None)))


def test_parse_system_message():
    ms = _msg("Zs", None, ["Zs", "s 072"])
    evts = parse_s3_message(ms)
    assert evts.category == DMPEventType.SYSTEM_MESSAGE
    assert evts.system_code == "072"
    assert isinstance(evts.system_text, (str, type(None)))
