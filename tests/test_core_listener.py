from __future__ import annotations

import pytest

from pydmp.core import ListenerProfilePush, PushTransportMode
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
    assert message.event.type_code == "CL"
    assert message.event.area == "003"
    assert message.event.area_name == "A3"
    assert message.event.user == "00000"
    assert message.event.user_name == "NO CODE REQUIRED"


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
    assert message.event.system_code == "086"
    assert message.event.system_text == "Local Programming"


def test_listener_profile_parses_host_output_checkin_with_interval() -> None:
    profile = ListenerProfilePush()
    state = profile.create_connection_state()

    action = profile.feed_data(state, HOST_OUTPUT_CHECKIN_FRAME)

    assert len(action.messages) == 1
    assert action.outbound_frames == [b"\x0212345\x06\r"]

    message = action.messages[0]
    assert message.account == "12345"
    assert message.wrapper_crc_hex == "71B8"
    assert message.wrapper_crc_calc == "71B8"
    assert message.wrapper_crc_valid is True
    assert message.event is None
    assert message.special is not None
    assert message.special.kind == "checkin_s070"
    assert message.special.interval_minutes == 5


def test_listener_profile_parses_host_output_checkin_without_interval() -> None:
    profile = ListenerProfilePush()
    state = profile.create_connection_state()

    action = profile.feed_data(state, HOST_OUTPUT_CHECKIN_BARE_FRAME)

    assert len(action.messages) == 1
    assert action.outbound_frames == [b"\x0212345\x06\r"]

    message = action.messages[0]
    assert message.account == "12345"
    assert message.event is None
    assert message.special is not None
    assert message.special.kind == "checkin_s070"
    assert message.special.interval_minutes is None


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
    assert message.event.type_code == "CL"

    secure_ack = parse_secure_s_frame(passphrase, data_action.outbound_frames[0])
    assert secure_ack.frame_type == SECURE_S_FRAME_TYPE_DATA
    assert secure_ack.payload == b"\x0212345\x06\r"


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
