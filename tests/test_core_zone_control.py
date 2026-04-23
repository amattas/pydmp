"""Readable tests for zone bypass and unbypass commands."""

import pytest

from pydmp.core import (
    CommandSessionManager,
    CorePanelClient,
    PanelEndpoint,
    SessionProfileBlankV2,
    SessionProfileSecureS,
    TransactionBypassZone,
    TransactionUnbypassZone,
    ZoneControlReply,
    normalize_zone_number,
    parse_zone_bypass_reply,
    parse_zone_unbypass_reply,
)
from pydmp.core.secure_s import (
    SECURE_S_FRAME_TYPE_DATA,
    SECURE_S_FRAME_TYPE_SETUP_REPLY,
    build_secure_s_frame,
    build_secure_s_setup_frame,
)


class FakeTransport:
    """Tiny scripted transport used to keep these tests focused on zone control."""

    def __init__(self, endpoint, scripted_replies=None):
        self.endpoint = endpoint
        self._scripted_replies = list(scripted_replies or [])
        self.is_connected = False
        self.requests = []

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def exchange(self, request: bytes, completion):
        del completion
        self.requests.append(request)
        if self._scripted_replies:
            return self._scripted_replies.pop(0)
        return b""


def make_transport_factory(scripted_replies=None):
    """Return a transport factory plus the created fake transports."""
    transports = []

    def factory(endpoint):
        transport = FakeTransport(endpoint, scripted_replies=scripted_replies)
        transports.append(transport)
        return transport

    return factory, transports


def test_normalize_zone_number():
    assert normalize_zone_number(1) == "001"
    assert normalize_zone_number("11") == "011"
    assert normalize_zone_number("999") == "999"

    with pytest.raises(ValueError):
        normalize_zone_number(0)

    with pytest.raises(ValueError):
        normalize_zone_number(1000)


def test_transaction_zone_control_shapes():
    bypass = TransactionBypassZone(1)
    unbypass = TransactionUnbypassZone("011")

    assert bypass.body == "!X001"
    assert bypass.label == "bypass_zone"
    assert bypass.parser is parse_zone_bypass_reply
    assert bypass.zone_number == "001"

    assert unbypass.body == "!Y011"
    assert unbypass.label == "unbypass_zone"
    assert unbypass.parser is parse_zone_unbypass_reply
    assert unbypass.zone_number == "011"


def test_parse_zone_control_replies():
    bypass_ok = parse_zone_bypass_reply(b"\x02@ 12345+X\r\x00")
    bypass_deny = parse_zone_bypass_reply(b"\x02@ 12345-XU\r\x00")
    bypass_guard = parse_zone_bypass_reply(b"\x02@ 12345-XP\r\x00")
    bypass_privilege = parse_zone_bypass_reply(b"\x02@ 12345-VV\r\x00")
    unbypass_ok = parse_zone_unbypass_reply(b"\x02@ 12345+Y\r\x00")
    unbypass_deny = parse_zone_unbypass_reply(b"\x02@ 12345-YU\r\x00")
    unbypass_privilege = parse_zone_unbypass_reply(b"\x02@ 12345-VV\r\x00")
    bypass_prefixed = parse_zone_bypass_reply(b"\x02@ 12345+!X\r\x00")

    assert bypass_ok == ZoneControlReply(command="X", acknowledged=True, detail=None)
    assert bypass_deny == ZoneControlReply(command="X", acknowledged=False, detail="U")
    assert bypass_guard == ZoneControlReply(command="X", acknowledged=False, detail="P")
    assert bypass_privilege == ZoneControlReply(command="X", acknowledged=False, detail="VV")
    assert unbypass_ok == ZoneControlReply(command="Y", acknowledged=True, detail=None)
    assert unbypass_deny == ZoneControlReply(command="Y", acknowledged=False, detail="U")
    assert unbypass_privilege == ZoneControlReply(command="Y", acknowledged=False, detail="VV")
    assert bypass_prefixed == ZoneControlReply(command="X", acknowledged=True, detail=None)


@pytest.mark.asyncio
async def test_core_panel_client_zone_control_over_blank_v2():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345+X\r\x00",
            b"\x02@ 12345+Y\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        bypass = await client.bypass_zone(1)
        unbypass = await client.unbypass_zone("001")

        assert bypass == ZoneControlReply(command="X", acknowledged=True, detail=None)
        assert unbypass == ZoneControlReply(command="Y", acknowledged=True, detail=None)
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345!X001\r"
        assert transports[0].requests[2] == b"@12345!Y001\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_core_panel_client_zone_control_over_secure_s():
    passphrase = "1234123412341234"
    setup_reply = build_secure_s_frame(
        passphrase,
        seq=0x2000,
        ack=7,
        frame_type=SECURE_S_FRAME_TYPE_SETUP_REPLY,
        payload=b"",
    )
    bypass_reply = build_secure_s_frame(
        passphrase,
        seq=0x2010,
        ack=0x0019,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=b"\x02@ 12345+X\r\x00",
    )
    unbypass_reply = build_secure_s_frame(
        passphrase,
        seq=0x2020,
        ack=0x002B,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=b"\x02@ 12345+Y\r\x00",
    )
    factory, transports = make_transport_factory(
        scripted_replies=[setup_reply, bypass_reply, unbypass_reply]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", passphrase=passphrase), session_profile=SessionProfileSecureS(), transport_factory=factory)

    try:
        bypass = await client.bypass_zone(1)
        unbypass = await client.unbypass_zone(1)

        assert bypass == ZoneControlReply(command="X", acknowledged=True, detail=None)
        assert unbypass == ZoneControlReply(command="Y", acknowledged=True, detail=None)
        assert transports[0].requests[0] == build_secure_s_setup_frame(passphrase)
        assert len(transports[0].requests) == 3
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manager_applies_zone_control_parser_automatically():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345-XU\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        transaction = await manager.submit(TransactionBypassZone(1))
        assert transaction.response == b"\x02@ 12345-XU\r\x00"
        assert transaction.parsed_response == ZoneControlReply(
            command="X",
            acknowledged=False,
            detail="U",
        )
        assert transaction.wire_requests == [b"@12345!X001\r"]
    finally:
        await manager.close()
