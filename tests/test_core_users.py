import pytest

from pydmp.core import (
    CommandSessionManager,
    CorePanelClient,
    PanelEndpoint,
    SessionProtocolError,
    SessionProfileBlankV2,
    TransactionQueryUsers,
    UserFlags,
    UserReply,
    parse_user_page,
)
from pydmp.core.users import (
    EXPERIMENTAL_WRITE_USER_MESSAGE,
    TransactionWriteUser,
    UserWriteReply,
    parse_user_write_reply,
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


def test_transaction_query_users_shape():
    transaction = TransactionQueryUsers()

    assert transaction.body == "?P=0000"
    assert transaction.label == "query_users"
    assert transaction.parser is None


def test_transaction_write_user_shape():
    transaction = TransactionWriteUser(
        4444,
        allow_experimental_write_user=True,
        code="4444",
        name="USER NAME 4444",
        profiles=[1],
        active=False,
        temporary=True,
        start_date="010220",
        end_date="010121",
    )

    assert transaction.label == "write_user"
    assert transaction.user_number == "4444"
    assert transaction.code == "4444FFFFFFFF"
    assert transaction.pin == "FFFFFF"
    assert transaction.profile_slots == ("001", "255", "255", "255")
    assert transaction.field_40_43 == "----"
    assert transaction.plain_record == "44444444FFFFFFFFFFFFFF001255255255010121----NNY010220USER NAME 4444"
    assert transaction.parser is parse_user_write_reply


def test_transaction_write_user_delete_shape():
    transaction = TransactionWriteUser(
        3,
        allow_experimental_write_user=True,
        name="TEST USER",
        profiles=[99, 8, 9, 10],
        delete=True,
        active=True,
        temporary=False,
        start_date="000000",
        end_date="000000",
    )

    assert transaction.delete is True
    assert transaction.code == "FFFFFFFFFFFF"
    assert transaction.pin == "FFFFFF"
    assert transaction.plain_record == "0003FFFFFFFFFFFFFFFFFF099008009010000000----YNN000000TEST USER"


def test_transaction_write_user_requires_experimental_opt_in():
    with pytest.raises(RuntimeError, match=EXPERIMENTAL_WRITE_USER_MESSAGE):
        TransactionWriteUser(
            3,
            name="TEST USER",
            profiles=[1],
        )


def test_transaction_write_user_rejects_user_0000():
    with pytest.raises(ValueError):
        TransactionWriteUser(
            0,
            allow_experimental_write_user=True,
            code="1234",
            name="BAD ZERO USER",
            profiles=[1],
        )


def test_parse_user_page():
    reply = (
        b"\x02@ 12345*P=0002DE6FD8ECF6FB7DBE5F051087043149555555----YNN555555USER NAME 0002"
        b"\x1e00038CFB188CC663DC53CC028115185092555555----YNN555555USER NAME 0003"
        b"\x1e----\r\x00"
    )

    page = parse_user_page(reply, account_number=12345)

    assert page.complete is True
    assert len(page.users) == 2

    user2 = page.users[0]
    assert user2.number == "0002"
    assert user2.code == "4321"
    assert user2.pin == ""
    assert user2.profiles == ("099", None, None, None)
    assert user2.end_date == "555555"
    assert user2.legacy_exp is None
    assert user2.flags == UserFlags(active=True, authority_1=False, temporary=False)
    assert user2.start_date == "555555"
    assert user2.name == "USER NAME 0002"

    user3 = page.users[1]
    assert user3.number == "0003"
    assert user3.code == "1234"
    assert user3.pin == "1234"
    assert user3.profiles == ("005", None, None, None)
    assert user3.end_date == "555555"
    assert user3.flags == UserFlags(active=True, authority_1=False, temporary=False)
    assert user3.start_date == "555555"
    assert user3.name == "USER NAME 0003"


def test_parse_user_page_empty_terminal():
    page = parse_user_page(b"\x02@ 12345*P=----\r\x00", account_number=12345)

    assert page.users == []
    assert page.complete is True


@pytest.mark.parametrize(
    "reply",
    [
        b"\x02@ 12345*P=\r\x00",
        (
            b"\x02@ 12345*P=0002DE6FD8ECF6FB7DBE5F051087043149555555----YNN555555USER NAME 0002"
            b"\x1e"
        ),
        (
            b"\x02@ 12345*P=0002DE6FD8ECF6FB7DBE5F051087043149555555----YNN555555USER NAME 0002"
            b"\x1e\x1e----\r\x00"
        ),
        (
            b"\x02@ 12345*P=0002DE6FD8ECF6FB7DBE5F051087043149555555----YNN555555USER NAME 0002"
            b"\x1e----\x1e00038CFB188CC663DC53CC028115185092555555----YNN555555USER NAME 0003\r\x00"
        ),
        (
            b"\x02@ 12345*P=0002DE6FD8ECF6FB7DBE5F051087043149555555----YNN555555USER NAME 0002"
            b"\x1e00038CFB188CC663DC53CC028115185092555555----YNN555555USER NAME 0003"
            b"\x1e99993D2D168BC5E2F1F8FC226063159207000000----YNN000000DEFAULT USER\x1e----\r\x00"
        ),
    ],
)
def test_parse_user_page_rejects_malformed_reply(reply):
    with pytest.raises(SessionProtocolError):
        parse_user_page(reply, account_number=12345)


def test_parse_user_write_reply():
    assert parse_user_write_reply(b"\x02@ 12345+P\r\x00") == UserWriteReply(
        acknowledged=True,
        detail=None,
    )
    assert parse_user_write_reply(b"\x02@ 12345-PV\r\x00") == UserWriteReply(
        acknowledged=False,
        detail="V",
    )


@pytest.mark.asyncio
async def test_core_panel_client_query_users():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            (
                b"\x02@ 12345*P=0002DE6FD8ECF6FB7DBE5F051087043149555555----YNN555555USER NAME 0002"
                b"\x1e00038CFB188CC663DC53CC028115185092555555----YNN555555USER NAME 0003"
                b"\x1e----\r\x00"
            ),
            (
                b"\x02@ 12345*P=000912A3371B0D06CFCD00122192224240555555----YNN555555USER NAME 0009"
                b"\x1e----\r\x00"
            ),
            (
                b"\x02@ 12345*P=----\r\x00"
            ),
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        reply = await client.query_users()
        assert isinstance(reply, UserReply)
        assert [user.number for user in reply.users] == ["0002", "0003", "0009"]
        assert reply.users[0].code == "4321"
        assert reply.users[1].pin == "1234"
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345?P=0000\r"
        assert transports[0].requests[2] == b"@12345?P=0004\r"
        assert transports[0].requests[3] == b"@12345?P=0010\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manager_query_users_paginates_until_empty_terminal_page():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            (
                b"\x02@ 12345*P=0002DE6FD8ECF6FB7DBE5F051087043149555555----YNN555555USER NAME 0002"
                b"\x1e00038CFB188CC663DC53CC028115185092555555----YNN555555USER NAME 0003"
                b"\x1e----\r\x00"
            ),
            (
                b"\x02@ 12345*P=000912A3371B0D06CFCD00122192224240555555----YNN555555USER NAME 0009"
                b"\x1e----\r\x00"
            ),
            (
                b"\x02@ 12345*P=----\r\x00"
            ),
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await manager.submit(TransactionQueryUsers())
        assert [user.number for user in transaction.parsed_response.users] == ["0002", "0003", "0009"]
        assert transaction.wire_requests == [
            b"@12345?P=0000\r",
            b"@12345?P=0004\r",
            b"@12345?P=0010\r",
        ]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_manager_query_users_stops_at_9999():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            (
                b"\x02@ 12345*P=44448EA18D462311884422111200100050010121----NNY010220USER NAME 4444"
                b"\x1e999982F4168BC5E2F1F8FC226063159207000000----YNN000000DEFAULT USER"
                b"\x1e----\r\x00"
            ),
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await manager.submit(TransactionQueryUsers())
        assert [user.number for user in transaction.parsed_response.users] == ["4444", "9999"]
        assert transaction.wire_requests == [b"@12345?P=0000\r"]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_manager_query_users_rejects_non_advancing_selector_walk():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            (
                b"\x02@ 12345*P=0002DE6FD8ECF6FB7DBE5F051087043149555555----YNN555555USER NAME 0002"
                b"\x1e00038CFB188CC663DC53CC028115185092555555----YNN555555USER NAME 0003"
                b"\x1e----\r\x00"
            ),
            (
                b"\x02@ 12345*P=00038CFB188CC663DC53CC028115185092555555----YNN555555USER NAME 0003"
                b"\x1e----\r\x00"
            ),
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionProtocolError, match="did not advance"):
            await manager.submit(TransactionQueryUsers())
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_manager_write_user_builds_known_good_record_and_parses_reply():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@  3734+V02003734\r",
            b"\x02@  3734+P\r\x00",
            b"\x02@  3734+V\r",
        ]
    )
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="3734", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await manager.submit(
            TransactionWriteUser(
                3,
                allow_experimental_write_user=True,
                code="4321",
                name="TEST USER",
                profiles=[99, 8, 9, 10],
                active=True,
                flag_2=False,
                temporary=False,
                start_date="000000",
                end_date="000000",
            )
        )
        assert transaction.plain_record == "00034321FFFFFFFFFFFFFF099008009010000000----YNN000000TEST USER"
        assert transaction.wire_record == "00038F474CA653A9D4EA75166106056018000000----YNN000000TEST USER"
        assert transaction.wire_requests == [
            b"@ 3734!P=00038F474CA653A9D4EA75166106056018000000----YNN000000TEST USER\x1e----00000\r"
        ]
        assert transaction.parsed_response == UserWriteReply(acknowledged=True, detail=None)
        assert transports[0].requests[1] == (
            b"@ 3734!P=00038F474CA653A9D4EA75166106056018000000----YNN000000TEST USER\x1e----00000\r"
        )
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_manager_write_user_delete_builds_known_good_record_and_parses_reply():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@  3734+V02003734\r",
            b"\x02@  3734+P\r\x00",
            b"\x02@  3734+V\r",
        ]
    )
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="3734", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await manager.submit(
            TransactionWriteUser(
                3,
                allow_experimental_write_user=True,
                name="TEST USER",
                profiles=[99, 8, 9, 10],
                delete=True,
                active=True,
                temporary=False,
                start_date="000000",
                end_date="000000",
            )
        )
        assert transaction.plain_record == "0003FFFFFFFFFFFFFFFFFF099008009010000000----YNN000000TEST USER"
        assert transaction.wire_record == "000333994CA653A9D4EA75166106056018000000----YNN000000TEST USER"
        assert transaction.wire_requests == [
            b"@ 3734!P=000333994CA653A9D4EA75166106056018000000----YNN000000TEST USER\x1e----00000\r"
        ]
        assert transaction.parsed_response == UserWriteReply(acknowledged=True, detail=None)
        assert transports[0].requests[1] == (
            b"@ 3734!P=000333994CA653A9D4EA75166106056018000000----YNN000000TEST USER\x1e----00000\r"
        )
    finally:
        await manager.close()
