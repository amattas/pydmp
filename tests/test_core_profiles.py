import pytest

from pydmp.core import (
    CommandSessionManager,
    CorePanelClient,
    PanelEndpoint,
    ProfilePage,
    ProfileRecord,
    ProfileReply,
    SessionProfileBlankV2,
    TransactionQueryProfiles,
    parse_profile_page,
)


class FakeTransport:
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
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

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
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await manager.submit(TransactionQueryProfiles())
        assert [profile.number for profile in transaction.parsed_response.profiles] == ["001"]
        assert transaction.wire_requests == [b"@12345?U000\r", b"@12345?U002\r"]
    finally:
        await manager.close()
