"""Readable tests for the new-core push listener and event parsers."""

from __future__ import annotations

import asyncio

import pytest

from pydmp.core import (
    DMPPushListener,
    ListenerProfilePush,
    PushParsedAccessEvent,
    PushParsedCheckinEvent,
    PushParsedScheduleEvent,
    PushParsedTaggedEvent,
    PushParsedUserCodeEvent,
    PushParsedZoneEvent,
    PushTransportMode,
    parse_push_event,
)
from pydmp.core.secure_s import (
    SECURE_S_FRAME_TYPE_DATA,
    SECURE_S_FRAME_TYPE_SETUP_REPLY,
    build_secure_s_frame,
    build_secure_s_setup_frame,
    parse_secure_s_frame,
)


CLEAR_ARM_FRAME = (
    b'\x025A72  12345 &    0Zq\\062\\t "CL\\u 00000"NO CODE REQUIRED\\a 003"A3              \\\r'
)

# These sample frames mirror the kinds of pushes stored in this project’s
# captures and listener logs. They give us realistic fixtures without requiring
# a live panel in the test suite.
HOST_OUTPUT_SYSTEM_FRAME = b"\x022841  12345 &    2Zs\\014\\t 086\\\r"
HOST_OUTPUT_CHECKIN_FRAME = b"\x0271B8  12345 s0700005 \r"
HOST_OUTPUT_CHECKIN_BARE_FRAME = b"\x02AB2A  12345 s070 \r"


def test_listener_profile_parses_clear_push_and_builds_s3_ack() -> None:
    profile = ListenerProfilePush()
    state = profile.create_connection_state()

    first = profile.feed_data(state, CLEAR_ARM_FRAME[:-1])
    assert first.messages == []
    assert first.outbound_frames == []

    second = profile.feed_data(state, CLEAR_ARM_FRAME[-1:])
    assert len(second.messages) == 1
    assert second.outbound_frames == [b"\x0212345\x06\r"]

    message = second.messages[0]
    assert message.transport_mode is PushTransportMode.CLEAR
    assert message.account == "12345"
    assert message.ack_frame == b"\x0212345\x06\r"
    assert message.event is not None
    assert message.event.definition == "Zq"
    assert message.event.group == "area"
    assert message.event.kind == "area_state"
    assert message.event.action == "armed"
    assert message.event.target_id == "003"
    assert message.event.actor_id == "00000"
    assert isinstance(message.event.parsed, PushParsedTaggedEvent)
    assert message.event.parser_name == "_parse_tagged_push_event"
    assert message.event.parsed.type_code == "CL"
    assert message.event.parsed.type_name == "armed"
    assert message.event.parsed.area == "003"
    assert message.event.parsed.area_name == "A3"
    assert message.event.parsed.user == "00000"
    assert message.event.parsed.user_name == "NO CODE REQUIRED"
    assert message.event.summary == "Area 003 A3 armed by 00000 NO CODE REQUIRED"


def test_listener_profile_parses_host_output_system_message() -> None:
    profile = ListenerProfilePush()
    state = profile.create_connection_state()

    action = profile.feed_data(state, HOST_OUTPUT_SYSTEM_FRAME)

    assert len(action.messages) == 1
    assert action.outbound_frames == [b"\x0212345\x06\r"]

    message = action.messages[0]
    assert message.account == "12345"
    assert message.wrapper_crc_hex == "2841"
    assert message.wrapper_crc_calc == "2841"
    assert message.wrapper_crc_valid is True
    assert message.event is not None
    assert message.event.definition == "Zs"
    assert isinstance(message.event.parsed, PushParsedTaggedEvent)
    assert message.event.parser_name == "_parse_tagged_push_event"
    assert message.event.parsed.system_code == "086"
    assert message.event.parsed.system_text == "Local Programming"


def test_listener_profile_does_not_ack_invalid_host_output_wrapper_crc() -> None:
    profile = ListenerProfilePush()
    state = profile.create_connection_state()

    action = profile.feed_data(state, b"\x020000  12345 &    2Zs\\014\\t 086\\\r")

    assert len(action.messages) == 1
    assert action.outbound_frames == []

    message = action.messages[0]
    assert message.account == "12345"
    assert message.wrapper_crc_hex == "0000"
    assert message.wrapper_crc_valid is False
    assert message.ack_frame is None
    assert message.event is not None
    assert message.event.definition == "Zs"


def test_listener_profile_parses_host_output_checkin_with_interval() -> None:
    profile = ListenerProfilePush()
    state = profile.create_connection_state()

    action = profile.feed_data(state, HOST_OUTPUT_CHECKIN_FRAME)

    assert len(action.messages) == 1
    assert action.outbound_frames == [b"\x0212345\x06\r"]

    message = action.messages[0]
    assert message.account == "12345"
    assert message.event is not None
    assert message.event.definition == "s070"
    assert isinstance(message.event.parsed, PushParsedCheckinEvent)
    assert message.event.parser_name == "_parse_checkin_s070_event"
    assert message.event.parsed.interval_minutes == 5
    assert message.wrapper_crc_hex == "71B8"
    assert message.wrapper_crc_calc == "71B8"
    assert message.wrapper_crc_valid is True
    assert message.special is None


def test_listener_profile_parses_host_output_checkin_without_interval() -> None:
    profile = ListenerProfilePush()
    state = profile.create_connection_state()

    action = profile.feed_data(state, HOST_OUTPUT_CHECKIN_BARE_FRAME)

    assert len(action.messages) == 1
    assert action.outbound_frames == [b"\x0212345\x06\r"]

    message = action.messages[0]
    assert message.account == "12345"
    assert message.event is not None
    assert message.event.definition == "s070"
    assert isinstance(message.event.parsed, PushParsedCheckinEvent)
    assert message.event.parsed.interval_minutes is None
    assert message.special is None


def test_parse_push_event_parses_zone_state_event_with_zone_target() -> None:
    normalized = b'8258  12345 &    1Zc\\020\\t "DO\\z 002\\'

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zc"
    assert event.group == "zone"
    assert event.kind == "zone_state"
    assert event.action == "open"
    assert event.type_name == "door open"
    assert event.target_id == "002"
    assert isinstance(event.parsed, PushParsedZoneEvent)
    assert event.parser_name == "_parse_zone_push_event"
    assert event.parsed.event_code == "020"
    assert event.parsed.type_code == "DO"
    assert event.parsed.target_kind == "zone"
    assert event.parsed.zone == "002"
    assert event.parsed.zone_name is None
    assert event.parsed.device is None


def test_parse_push_event_parses_zone_state_event_with_device_target() -> None:
    normalized = b'46F0  12345 &    0Zc\\020\\t "OF\\v 580\\'

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zc"
    assert event.kind == "zone_state"
    assert event.action == "off"
    assert event.type_name == "output off"
    assert event.target_id == "580"
    assert isinstance(event.parsed, PushParsedZoneEvent)
    assert event.parsed.event_code == "020"
    assert event.parsed.type_code == "OF"
    assert event.parsed.target_kind == "device"
    assert event.parsed.zone is None
    assert event.parsed.device == "580"


def test_parse_push_event_parses_bypass_event() -> None:
    normalized = (
        b'1142  12345 &    0Zx\\085\\t "BU\\z 502"FRONT DOOR      '
        b'\\u 32764"REMOTE USER     \\a 001"PERIMETER       \\'
    )

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zx"
    assert event.kind == "zone_bypass"
    assert event.action == "bypass"
    assert event.type_name == "burglary"
    assert event.actor_id == "32764"
    assert isinstance(event.parsed, PushParsedZoneEvent)
    assert event.parsed.event_code == "085"
    assert event.parsed.type_code == "BU"
    assert event.parsed.target_kind == "zone"
    assert event.parsed.zone == "502"
    assert event.parsed.zone_name == "FRONT DOOR"
    assert event.parsed.area == "001"
    assert event.parsed.actor_user == "32764"
    assert event.summary == "Zone 502 FRONT DOOR bypass (burglary) by 32764 REMOTE USER"


def test_parse_push_event_parses_alarm_event() -> None:
    normalized = b'9545  12345 &    0Za\\037\\t "FI\\z 009"Z9FIRE          \\'

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Za"
    assert event.kind == "zone_alarm"
    assert event.action == "alarm"
    assert event.type_name == "fire"
    assert event.target_id == "009"
    assert event.target_name == "Z9FIRE"
    assert event.summary == "Zone 009 Z9FIRE alarm (fire)"


def test_parse_push_event_parses_trouble_and_restore_events() -> None:
    trouble = parse_push_event("12345", b'01EF  12345 &    0Zt\\037\\t "SV\\z 580"SUP             \\')
    restore = parse_push_event("12345", b'4D6F  12345 &    0Zr\\037\\t "SV\\z 580"SUP             \\')

    assert trouble is not None
    assert trouble.kind == "zone_trouble"
    assert trouble.action == "trouble"
    assert trouble.type_name == "supervisory"
    assert trouble.summary == "Zone 580 SUP trouble (supervisory)"

    assert restore is not None
    assert restore.kind == "zone_restore"
    assert restore.action == "restore"
    assert restore.type_name == "supervisory"
    assert restore.summary == "Zone 580 SUP restore (supervisory)"


def test_parse_push_event_parses_access_event() -> None:
    normalized = (
        b'BEEF  12345 &    0Zj\\070\\t "IC\\v 001"KEYPAD          '
        b'\\u 00000"  INVALID CODE  \\eu"0016\\'
    )

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zj"
    assert event.group == "access"
    assert event.kind == "access_event"
    assert event.action == "invalid_code_denied"
    assert event.type_name == "invalid code access denied"
    assert isinstance(event.parsed, PushParsedAccessEvent)
    assert event.parser_name == "_parse_access_push_event"
    assert event.parsed.event_code == "070"
    assert event.parsed.type_code == "IC"
    assert event.parsed.device == "001"
    assert event.parsed.device_name == "KEYPAD"
    assert event.parsed.actor_user == "00000"
    assert event.parsed.entered_code == "0016"
    assert event.summary == "Device 001 KEYPAD invalid code access denied for 00000 INVALID CODE using code 0016"


def test_parse_push_event_parses_schedule_event() -> None:
    normalized = (
        b'BEEF  12345 &    0Zl\\083\\t "01\\n "SCHEDULE NAME 01'
        b'\\io09:00"MON\\ic10:20"MON\\u 00001"USER NAME 0001  \\'
    )

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zl"
    assert event.group == "schedule"
    assert event.kind == "schedule_event"
    assert event.action == "schedule_update"
    assert isinstance(event.parsed, PushParsedScheduleEvent)
    assert event.parser_name == "_parse_schedule_push_event"
    assert event.parsed.event_code == "083"
    assert event.parsed.type_code == "01"
    assert event.parsed.schedule_name == "SCHEDULE NAME 01"
    assert event.parsed.open_time == "09:00"
    assert event.parsed.open_day == "MON"
    assert event.parsed.close_time == "10:20"
    assert event.parsed.close_day == "MON"
    assert event.parsed.actor_user == "00001"
    assert event.summary == "SCHEDULE NAME 01 open 09:00 MON close 10:20 MON by 00001 USER NAME 0001"


def test_parse_push_event_parses_schedule_event_without_name() -> None:
    normalized = (
        b'BEEF  12345 &    0Zl\\063\\t "TE\\io00:00"MON\\ic12:14"MON'
        b'\\u 00001"USER NAME 0001  \\'
    )

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zl"
    assert isinstance(event.parsed, PushParsedScheduleEvent)
    assert event.parsed.event_code == "063"
    assert event.parsed.type_code == "TE"
    assert event.parsed.schedule_name is None
    assert event.parsed.open_time == "00:00"
    assert event.parsed.close_time == "12:14"
    assert event.parsed.actor_user == "00001"


def test_parse_push_event_parses_user_code_event() -> None:
    normalized = (
        b'BEEF  12345 &    0Zu\\143\\t "AD\\um00001"USER NAME 0001  '
        b'\\u 09999"DEFAULT USER    '
        b'\\P18DD36F4FA2E6A2236CF87ECADC17B3D7F64892741C9C7FFEDB60D5979348C360000000000000\\'
    )

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zu"
    assert event.group == "user_code"
    assert event.kind == "user_code_event"
    assert event.action == "added"
    assert event.type_name == "added user code"
    assert isinstance(event.parsed, PushParsedUserCodeEvent)
    assert event.parser_name == "_parse_user_code_push_event"
    assert event.parsed.event_code == "143"
    assert event.parsed.type_code == "AD"
    assert event.parsed.subject_user == "00001"
    assert event.parsed.subject_user_name == "USER NAME 0001"
    assert event.parsed.actor_user == "09999"
    assert event.parsed.actor_user_name == "DEFAULT USER"
    assert event.parsed.protected_hex is not None
    assert event.parsed.protected_hex.startswith("18DD36F4")
    assert event.summary == "User 00001 USER NAME 0001 added by 09999 DEFAULT USER"


def test_parse_push_event_parses_arming_event_path_info_and_qualifier() -> None:
    normalized = (
        b'5AFE  12345 Zq\\070\\t "CL\\u 00000"NO CODE REQUIRED'
        b'\\a 003"A3              \\c 01"NP\\'
    )

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zq"
    assert event.kind == "area_state"
    assert isinstance(event.parsed, PushParsedTaggedEvent)
    assert event.parsed.event_code == "070"
    assert event.parsed.type_code == "CL"
    assert event.parsed.area == "003"
    assert event.parsed.path_number == "01"
    assert event.parsed.path_transport == "N"
    assert event.parsed.path_role == "P"
    assert event.parsed.event_qualifier is None


def test_parse_push_event_parses_arming_event_plain_qualifier() -> None:
    normalized = (
        b'D76E  12345 &    0Zq\\068\\t "CL\\u 00000"NO CODE REQUIRED'
        b'\\a 001"PERIMETER       \\e "AC\\'
    )

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zq"
    assert isinstance(event.parsed, PushParsedTaggedEvent)
    assert event.parsed.event_code == "068"
    assert event.parsed.type_code == "CL"
    assert event.parsed.area == "001"
    assert event.parsed.event_qualifier == "AC"
    assert event.parsed.qualifier_name == "all_areas_armed"
    assert event.parsed.path_number is None


def test_parse_push_event_parses_system_message_path_info() -> None:
    normalized = b'ABC7  12345 Zs\\022\\t 086\\c 01"NP\\'

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zs"
    assert event.group == "system"
    assert event.kind == "system_message"
    assert event.action == "message"
    assert event.summary == "System message Local Programming"
    assert isinstance(event.parsed, PushParsedTaggedEvent)
    assert event.parsed.system_code == "086"
    assert event.parsed.path_number == "01"
    assert event.parsed.path_transport == "N"
    assert event.parsed.path_role == "P"


def test_parse_push_event_returns_raw_only_for_invalid_family_shape() -> None:
    normalized = b'5A72  12345 &    0Zc\\020\\t "XX\\z 002\\'

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zc"
    assert event.parsed is None
    assert event.parser_name == "_parse_zone_push_event"


def test_listener_profile_handles_secure_setup_and_secure_push_ack() -> None:
    passphrase = "3333333333333333"
    profile = ListenerProfilePush(secure_passphrases=[passphrase])
    state = profile.create_connection_state()

    setup_action = profile.feed_data(state, build_secure_s_setup_frame(passphrase))
    assert setup_action.messages == []
    assert len(setup_action.outbound_frames) == 1

    setup_reply = parse_secure_s_frame(passphrase, setup_action.outbound_frames[0])
    assert setup_reply.frame_type == SECURE_S_FRAME_TYPE_SETUP_REPLY

    secure_data = build_secure_s_frame(
        passphrase,
        seq=7,
        ack=0,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=CLEAR_ARM_FRAME,
    )
    data_action = profile.feed_data(state, secure_data)

    assert len(data_action.messages) == 1
    assert len(data_action.outbound_frames) == 1

    message = data_action.messages[0]
    assert message.transport_mode is PushTransportMode.SECURE_S
    assert message.account == "12345"
    assert message.event is not None
    assert message.event.definition == "Zq"
    assert isinstance(message.event.parsed, PushParsedTaggedEvent)
    assert message.event.parsed.type_code == "CL"

    secure_ack = parse_secure_s_frame(passphrase, data_action.outbound_frames[0])
    assert secure_ack.frame_type == SECURE_S_FRAME_TYPE_DATA
    assert secure_ack.payload == b"\x0212345\x06\r"


def test_secure_listener_signals_passphrase_mismatch_without_ack() -> None:
    profile = ListenerProfilePush(secure_passphrases=["4444444444444444"])
    state = profile.create_connection_state()

    action = profile.feed_data(state, build_secure_s_setup_frame("3333333333333333"))

    assert action.outbound_frames == []
    assert action.close_connection is True
    assert len(action.messages) == 1
    message = action.messages[0]
    assert message.transport_mode is PushTransportMode.SECURE_S
    assert message.event is None
    assert message.special is not None
    assert message.special.kind == "secure_passphrase_mismatch"
    assert message.special.detail == "Secure !!S frame did not match any configured passphrase"


def test_clear_listener_signals_secure_mode_mismatch_without_ack() -> None:
    profile = ListenerProfilePush()
    state = profile.create_connection_state()

    action = profile.feed_data(state, build_secure_s_setup_frame("3333333333333333"))

    assert action.outbound_frames == []
    assert action.close_connection is True
    assert len(action.messages) == 1
    message = action.messages[0]
    assert message.transport_mode is PushTransportMode.SECURE_S
    assert message.event is None
    assert message.special is not None
    assert message.special.kind == "listener_mode_mismatch"
    assert message.special.detail == "Received secure !!S push traffic on a clear-only listener"


def test_secure_listener_signals_clear_mode_mismatch_without_ack() -> None:
    profile = ListenerProfilePush(secure_passphrases=["3333333333333333"])
    state = profile.create_connection_state()

    action = profile.feed_data(state, CLEAR_ARM_FRAME)

    assert action.outbound_frames == []
    assert action.close_connection is True
    assert len(action.messages) == 1
    message = action.messages[0]
    assert message.transport_mode is PushTransportMode.CLEAR
    assert message.event is None
    assert message.special is not None
    assert message.special.kind == "listener_mode_mismatch"
    assert message.special.detail == "Received clear push traffic on a secure-only listener"


def test_parse_push_event_returns_raw_only_for_unknown_code() -> None:
    normalized = b'5A72  12345 &    0Zm\\999\\t "??\\'

    event = parse_push_event("12345", normalized)

    assert event is not None
    assert event.definition == "Zm"
    assert event.raw == 'Zm\\999\\t "??\\'
    assert event.parsed is None
    assert event.parser_name is None


def test_listener_profile_supports_custom_event_parser_registration() -> None:
    profile = ListenerProfilePush()

    def parse_zx(account: str, payload: bytes, raw: str) -> dict[str, str]:
        return {
            "account": account,
            "payload": payload.decode("ascii", errors="replace"),
            "raw": raw,
        }

    profile.register_event_parser("Zx", parse_zx)
    state = profile.create_connection_state()

    action = profile.feed_data(state, b'\x025A72  12345 &    0Zx\\999\\t "??\\\r')

    assert len(action.messages) == 1
    message = action.messages[0]
    assert message.event is not None
    assert message.event.definition == "Zx"
    assert message.event.parser_name == "parse_zx"
    assert message.event.summary == 'Zx\\999\\t "??\\'
    assert message.event.parsed == {
        "account": "12345",
        "payload": 'Zx\\999\\t "??\\',
        "raw": 'Zx\\999\\t "??\\',
    }


@pytest.mark.asyncio
async def test_listener_dispatch_isolates_callback_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = ListenerProfilePush()
    state = profile.create_connection_state()
    action = profile.feed_data(state, CLEAR_ARM_FRAME)
    message = action.messages[0]

    listener = DMPPushListener(profile=profile)
    delivered: list[object] = []

    def bad_callback(_message):
        raise RuntimeError("boom")

    def good_callback(push_message):
        delivered.append(push_message)

    captured: list[dict[str, object]] = []
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "call_exception_handler", lambda context: captured.append(context))

    listener.register_callback(bad_callback)
    listener.register_callback(good_callback)

    await listener._dispatch(message)

    assert delivered == [message]
    assert len(captured) == 1
    assert captured[0]["message"] == "Unhandled DMP push listener callback exception"
    assert isinstance(captured[0]["exception"], RuntimeError)


@pytest.mark.asyncio
async def test_listener_stop_closes_active_client_writers() -> None:
    class FakeServer:
        def __init__(self) -> None:
            self.closed = False
            self.wait_closed_called = False

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            self.wait_closed_called = True

    class FakeWriter:
        def __init__(self) -> None:
            self.closed = False
            self.wait_closed_called = False

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            self.wait_closed_called = True

    listener = DMPPushListener()
    server = FakeServer()
    writer = FakeWriter()

    listener._server = server  # type: ignore[assignment]
    listener._client_writers.add(writer)  # type: ignore[arg-type]

    await listener.stop()

    assert listener._server is None
    assert server.closed is True
    assert server.wait_closed_called is True
    assert writer.closed is True
    assert writer.wait_closed_called is True
