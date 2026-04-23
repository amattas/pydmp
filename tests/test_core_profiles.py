"""Readable tests for `?U` profile queries and profile parsing helpers."""

import pytest

from pydmp.core import (
    CommandSessionManager,
    CorePanelClient,
    PanelEndpoint,
    ProfilePage,
    ProfileRecord,
    ProfileReply,
    SessionProtocolError,
    SessionProfileBlankV2,
    TransactionQueryProfiles,
    parse_profile_page,
)


class FakeTransport:
    """Tiny scripted transport used to keep these tests focused on profile logic."""

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


def test_transaction_query_profiles_shape():
    transaction = TransactionQueryProfiles()

    assert transaction.body == "?U000"
    assert transaction.label == "query_profiles"
    assert transaction.parser is None


def test_parse_profile_page():
    reply = (
        b"\x02@ 12345*U0000000000000000000000000000000000000000000000000000001001001001"
        b"\x1e001C000000000000000000477B8340----------------000000000000000000MASTER"
        b"\x1e----\r\x00"
    )

    page = parse_profile_page(reply)

    assert page == ProfilePage(
        profiles=[
            ProfileRecord(
                number="000",
                areas_mask="00000000",
                access_areas_mask="00000000",
                output_group="000",
                menu_options="00000000",
                field_30_45="0000000000000000",
                rearm_delay="000",
                field_49_63="000001001001001",
                name="",
            ),
            ProfileRecord(
                number="001",
                areas_mask="C0000000",
                access_areas_mask="00000000",
                output_group="000",
                menu_options="477B8340",
                field_30_45="----------------",
                rearm_delay="000",
                field_49_63="000000000000000",
                name="MASTER",
            ),
        ],
        has_terminal_marker=True,
        raw_reply=reply,
    )


def test_parse_empty_profile_page():
    reply = b"\x02@ 12345*U----\r\x00"

    page = parse_profile_page(reply)

    assert page == ProfilePage(profiles=[], has_terminal_marker=True, raw_reply=reply)


def test_profile_record_breaks_into_known_elements():
    record = ProfileRecord(
        number="007",
        areas_mask="AA000000",
        access_areas_mask="0F000000",
        output_group="001",
        menu_options="00005F5D",
        field_30_45="0102030405060708",
        rearm_delay="090",
        field_49_63="111222333444555",
        name="PROFILE NAME 07",
    )

    assert record.arm_disarm_areas_mask == "AA000000"
    assert record.arm_disarm_areas == (1, 3, 5, 7)
    assert record.access_areas == (5, 6, 7, 8)
    assert record.output_group_number == 1
    assert record.menu_options_raw == "00005F5D"
    assert record.menu_option_byte_1 == 0x00
    assert record.menu_option_byte_2 == 0x00
    assert record.menu_option_byte_3 == 0x5F
    assert record.menu_option_byte_4 == 0x5D
    assert record.schedules_permission is True
    assert record.time_permission is True
    assert record.display_events is True
    assert record.service_request_permission is True
    assert record.fire_drill_permission is True
    assert record.anti_passback_permission is True
    assert record.arm_permission is False
    assert record.easy_arm_disarm is True
    assert record.card_plus_pin is True
    assert record.wifi_setup is True
    assert record.technician_user is True
    assert record.access_schedule_cells == ("01", "02", "03", "04", "05", "06", "07", "08")
    assert record.first_access_schedule == "01"
    assert record.eighth_access_schedule == "08"
    assert record.tail_01 == "090"
    assert record.tail_02 == "111"
    assert record.tail_03 == "222"
    assert record.tail_04 == "333"
    assert record.tail_05 == "444"
    assert record.tail_06 == "555"


@pytest.mark.parametrize(
    "reply",
    [
        b"\x02@ 12345*U\r\x00",
        (
            b"\x02@ 12345*U001C000000000000000000477B8340----------------000000000000000000MASTER"
            b"\x1e"
        ),
        (
            b"\x02@ 12345*U001C000000000000000000477B8340----------------000000000000000000MASTER"
            b"\x1e\x1e----\r\x00"
        ),
        (
            b"\x02@ 12345*U001C000000000000000000477B8340----------------000000000000000000MASTER"
            b"\x1e----\x1e002E0000000000000000007F098440----------------000000000000000000PROFILE NAME 02\r\x00"
        ),
        (
            b"\x02@ 12345*U001C000000000000000000477B8340----------------000000000000000000MASTER"
            b"\x1e002E0000000000000000007F098440----------------000000000000000000PROFILE NAME 02"
            b"\x1e003E0000000000000000007F098440----------------000000000000000000PROFILE NAME 03"
            b"\x1e004E0000000000000000007F1D8440----------------000000000000000000PROFILE NAME 04"
            b"\x1e005E000000000000000000FF1D8440----------------000000000000000000PROFILE NAME 05"
            b"\x1e006E000000000000000000FF9F8440----------------000000000000000000PROFILE NAME 06"
            b"\x1e----\r\x00"
        ),
        b"\x02@ 12345*U001C000000000000000000477B8340\r\x00",
    ],
)
def test_parse_profile_page_rejects_malformed_reply(reply):
    with pytest.raises(SessionProtocolError):
        parse_profile_page(reply)


@pytest.mark.asyncio
async def test_core_panel_client_query_profiles():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            (
                b"\x02@ 12345*U0000000000000000000000000000000000000000000000000000001001001001"
                b"\x1e001C000000000000000000477B8340----------------000000000000000000MASTER"
                b"\x1e----\r\x00"
            ),
            (
                b"\x02@ 12345*U099FFFFFFFFFFFFFFFF010FFFF9F68----------------000000000000000000PROFILE NAME 99"
                b"\x1e----\r\x00"
            ),
            b"\x02@ 12345*U----\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        reply = await client.query_profiles()
        assert isinstance(reply, ProfileReply)
        assert [profile.number for profile in reply.profiles] == ["000", "001", "099"]
        assert reply.profiles[1].name == "MASTER"
        assert reply.profiles[2].output_group == "010"
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345?U000\r"
        assert transports[0].requests[2] == b"@12345?U002\r"
        assert transports[0].requests[3] == b"@12345?U100\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manager_query_profiles_stops_on_empty_page():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            (
                b"\x02@ 12345*U001C000000000000000000477B8340----------------000000000000000000MASTER"
                b"\x1e----\r\x00"
            ),
            b"\x02@ 12345*U----\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        transaction = await manager.submit(TransactionQueryProfiles())
        assert [profile.number for profile in transaction.parsed_response.profiles] == ["001"]
        assert transaction.wire_requests == [b"@12345?U000\r", b"@12345?U002\r"]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_manager_query_profiles_rejects_non_advancing_selector_walk():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            (
                b"\x02@ 12345*U001C000000000000000000477B8340----------------000000000000000000MASTER"
                b"\x1e----\r\x00"
            ),
            (
                b"\x02@ 12345*U001C000000000000000000477B8340----------------000000000000000000MASTER"
                b"\x1e----\r\x00"
            ),
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        with pytest.raises(SessionProtocolError, match="did not advance"):
            await manager.submit(TransactionQueryProfiles())
    finally:
        await manager.close()
