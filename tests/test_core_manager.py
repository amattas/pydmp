import asyncio

import pytest

from pydmp.core import (
    CommandSessionManager,
    PanelEndpoint,
    SessionHandshakeError,
    SessionMode,
    SessionProfileBlankV2,
    SessionProfileKeyedV2,
    SessionProfileSecureS,
    SessionProfileV30,
    SessionProfileV31,
    Transaction,
    TransactionParseError,
    TransactionQueryAreas,
    ack_or_deny,
    payload_required,
)
from pydmp.core.sessions import build_session_profile
from pydmp.core.wrapped_v3 import (
    build_v30_auth_body,
    build_v31_auth_body,
    encode_account_v3_frame,
    wrap_v3_body,
)


class FakeTransport:
    def __init__(self, endpoint, scripted_replies=None, scripted_errors=None):
        self.endpoint = endpoint
        self._scripted_replies = list(scripted_replies or [])
        self._scripted_errors = list(scripted_errors or [])
        self.is_connected = False
        self.requests = []
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self):
        self.connect_calls += 1
        self.is_connected = True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.is_connected = False

    async def exchange(self, request: bytes, completion):
        del completion
        self.requests.append(request)
        if self._scripted_errors:
            err = self._scripted_errors.pop(0)
            raise err
        if self._scripted_replies:
            return self._scripted_replies.pop(0)
        return b""


def make_transport_factory(scripted_replies=None, scripted_errors=None):
    transports = []

    def factory(endpoint):
        transport = FakeTransport(
            endpoint,
            scripted_replies=scripted_replies,
            scripted_errors=scripted_errors,
        )
        transports.append(transport)
        return transport

    return factory, transports


def encode_wrapped_reply(account_field: str, body: str, trailer: str = " ") -> bytes:
    wrapped = wrap_v3_body(body, trailer)
    return (
        b"\x02@"
        + account_field.encode("ascii")
        + wrapped.body
        + bytes([wrapped.trailer_byte])
        + f"{wrapped.checksum:04X}".encode("ascii")
        + b"\r\x00"
    )


@pytest.mark.asyncio
async def test_blank_v2_manager_executes_one_transaction():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r",
            b"\x02@ 12345+V\r",
        ]
    )
    endpoint = PanelEndpoint(host="192.168.111.2", account="12345", idle_disconnect_seconds=0.01)
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    transaction = await manager.execute("?WA01", label="area_status")

    assert transaction.session_mode is SessionMode.BLANK_V2
    assert transaction.wire_request == b"@12345?WA01\r"
    assert transaction.response == b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r"
    assert transaction.had_reply is True
    assert transports[0].requests[0] == b"@12345!V2                \r"
    assert transports[0].requests[1] == b"@12345?WA01\r"

    await manager.close()
    assert transports[0].requests[-1] == b"@12345!V0\r"


@pytest.mark.asyncio
async def test_manager_closes_idle_session_and_reopens_for_later_work():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WB...\r",
            b"\x02@ 12345+V\r",
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA...\r",
            b"\x02@ 12345+V\r",
        ]
    )
    endpoint = PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01)
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    first = await manager.execute("?WB**Y001", label="zones")
    assert first.response == b"\x02@ 12345*WB...\r"

    await asyncio.sleep(0.03)
    assert transports[0].disconnect_calls >= 1

    second = await manager.execute("?WA01", label="areas")
    assert second.response == b"\x02@ 12345*WA...\r"
    assert transports[0].connect_calls == 2

    await manager.close()


@pytest.mark.asyncio
async def test_blank_v2_handshake_rejects_negative_v_reply():
    factory, transports = make_transport_factory(scripted_replies=[b"\x02@ 12345-VC\r"])
    endpoint = PanelEndpoint(host="panel", account="12345")
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError):
            await manager.execute("?WA01")
        assert transports[0].requests == [b"@12345!V2                \r"]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_blank_v2_handshake_soft_passes_non_fatal_denial():
    """Bench pcaps show `-VB` precedes real command traffic on the same session."""
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345-VB\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r",
            b"\x02@ 12345+V\r",
        ]
    )
    endpoint = PanelEndpoint(host="panel", account="12345")
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await manager.execute("?WA01", label="area_status")
        assert transaction.response == b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r"
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345?WA01\r"
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_blank_v2_handshake_rejects_unknown_denial():
    """Only `-VB` is bench-confirmed non-fatal; every other `-V*` must raise."""
    factory, transports = make_transport_factory(scripted_replies=[b"\x02@ 12345-VA\r"])
    endpoint = PanelEndpoint(host="panel", account="12345")
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError, match=r"Blank V2 authentication denied by panel \(-VA\)"):
            await manager.execute("?WA01")
        assert transports[0].requests == [b"@12345!V2                \r"]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_blank_v2_handshake_accepts_bare_plus_v_banner():
    """Older pydmp-style panels reply to `!V2` with a plain `+V`, no version digit."""
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r",
            b"\x02@ 12345+V\r",
        ]
    )
    endpoint = PanelEndpoint(host="panel", account="12345")
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await manager.execute("?WA01", label="area_status")
        assert transaction.response == b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r"
        assert transports[0].requests[0] == b"@12345!V2                \r"
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_blank_v2_handshake_treats_fatal_after_soft_as_fatal():
    """A buffered reply with `-VB` followed by `-VC` must raise on the fatal code."""
    factory, transports = make_transport_factory(
        scripted_replies=[b"\x02@ 12345-VB\r\x02@ 12345-VC\r"]
    )
    endpoint = PanelEndpoint(host="panel", account="12345")
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError, match=r"Blank V2 authentication denied by panel \(-VC\)"):
            await manager.execute("?WA01")
        assert transports[0].requests == [b"@12345!V2                \r"]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_manager_drains_current_queue_on_session_error_but_can_recover():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA...\r",
            b"\x02@ 12345+V\r",
        ],
        scripted_errors=[
            SessionHandshakeError("synthetic failure during queued work"),
        ],
    )
    endpoint = PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.5)
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    tx1 = Transaction(body="?WA01", completion=payload_required(), label="first")
    tx2 = Transaction(body="!X001", completion=ack_or_deny(), label="second")

    first_task = asyncio.create_task(manager.submit(tx1))
    second_task = asyncio.create_task(manager.submit(tx2))

    results = await asyncio.gather(first_task, second_task, return_exceptions=True)
    assert isinstance(results[0], SessionHandshakeError)
    assert isinstance(results[1], SessionHandshakeError)
    assert transports[0].disconnect_calls >= 1

    recovered = await manager.execute("?WA01", label="after_recovery")
    assert recovered.response == b"\x02@ 12345*WA...\r"
    assert transports[0].connect_calls == 2

    await manager.close()


@pytest.mark.asyncio
async def test_transaction_parse_error_does_not_poison_the_session():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r",
            b"\x02@ 12345+V\r",
        ]
    )
    endpoint = PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=10.0)
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    def broken_parser(reply: bytes) -> object:
        del reply
        raise ValueError("synthetic parse failure")

    try:
        with pytest.raises(TransactionParseError):
            await manager.submit(
                Transaction(
                    body="?WA01",
                    completion=payload_required(),
                    label="bad_parse",
                    parser=broken_parser,
                )
            )

        recovered = await manager.execute("?WA01", label="after_parse_failure")
        assert recovered.response == b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r"
        assert transports[0].connect_calls == 1
    finally:
        await manager.close()


def test_scaffolded_profiles_can_be_built_explicitly():
    assert build_session_profile(SessionMode.BLANK_V2).mode is SessionMode.BLANK_V2
    assert build_session_profile(SessionMode.KEYED_V2, remote_key="0123456789ABCDEF").mode is SessionMode.KEYED_V2
    assert build_session_profile(SessionMode.V31, compare_material="        ").mode is SessionMode.V31
    assert build_session_profile(SessionMode.V30, code="1234", panel_serial="00172CD2").mode is SessionMode.V30
    assert build_session_profile(SessionMode.SECURE_S, passphrase="12341234").mode is SessionMode.SECURE_S


def test_panel_endpoint_applies_light_validation():
    endpoint = PanelEndpoint(
        host=" 192.168.111.2 ",
        account=" 1 ",
        port=8011,
        remote_key="01234567",
        v31_compare_material="ABC",
        panel_serial="00172cd2",
        user_code="1234",
        passphrase="12341234",
        v30_tail4="0000",
    )

    assert endpoint.host == "192.168.111.2"
    assert endpoint.account == "1"
    assert endpoint.normalized_account == "    1"
    assert endpoint.remote_key == "01234567"
    assert endpoint.v31_compare_material == "ABC       "
    assert endpoint.panel_serial == "00172CD2"
    assert endpoint.user_code == "1234"
    assert endpoint.passphrase == "12341234"
    assert endpoint.v30_tail4 == "0000"


@pytest.mark.parametrize(
    ("kwargs", "expected_message"),
    [
        ({"host": "", "account": "12345"}, "Host must not be empty"),
        ({"host": "panel", "account": "ABCDE"}, "Account must be 1..5 digits"),
        ({"host": "panel", "account": "123456"}, "Account must be 1..5 digits"),
        ({"host": "panel", "account": "12345", "port": 0}, "Port must be in 1..65535"),
        ({"host": "panel", "account": "12345", "connect_timeout": 0}, "connect_timeout must be greater than 0"),
        ({"host": "panel", "account": "12345", "idle_disconnect_seconds": -1}, "idle_disconnect_seconds must be >= 0"),
        ({"host": "panel", "account": "12345", "rate_limit_seconds": -1}, "rate_limit_seconds must be >= 0"),
        ({"host": "panel", "account": "12345", "remote_key": "short"}, "Remote key must be 8..16 ASCII characters"),
        ({"host": "panel", "account": "12345", "remote_key": "0123456789ABCDEFG"}, "Remote key must be 8..16 ASCII characters"),
        ({"host": "panel", "account": "12345", "panel_serial": "xyz"}, "Panel serial must be exactly 8 uppercase hex chars"),
        ({"host": "panel", "account": "12345", "user_code": "12A4"}, "V30 code must be numeric"),
        ({"host": "panel", "account": "12345", "passphrase": "12345678901234567"}, "Secure passphrase exceeds 16 bytes"),
        ({"host": "panel", "account": "12345", "v30_tail4": "000"}, "V30 tail4 must be exactly 4 ASCII bytes"),
    ],
)
def test_panel_endpoint_rejects_bad_input(kwargs, expected_message):
    with pytest.raises(ValueError, match=expected_message):
        PanelEndpoint(**kwargs)


@pytest.mark.asyncio
async def test_scaffolded_profiles_raise_not_implemented_when_used():
    factory, _transports = make_transport_factory()
    endpoint = PanelEndpoint(host="panel", account="12345")
    secure_s_manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileSecureS(passphrase="12341234"),
        transport_factory=factory,
    )
    missing_key_manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileKeyedV2(remote_key=""),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError):
            await missing_key_manager.execute("?WA01")
    finally:
        await missing_key_manager.close()
        await secure_s_manager.close()


@pytest.mark.asyncio
async def test_keyed_v2_manager_executes_wa_transaction():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r",
            b"\x02@ 12345+V\r",
        ]
    )
    endpoint = PanelEndpoint(
        host="panel",
        account="12345",
        remote_key="0123456789ABCDEF",
        idle_disconnect_seconds=0.01,
    )
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileKeyedV2(remote_key="0123456789ABCDEF"),
        transport_factory=factory,
    )

    transaction = await manager.submit(TransactionQueryAreas())

    assert transaction.session_mode is SessionMode.KEYED_V2
    assert transaction.response == b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r"
    assert transaction.parsed_response is not None
    assert transaction.parsed_response.areas[0].name == "PERIMETER"
    assert transports[0].requests[0] == b"@12345!V20123456789ABCDEF\r"
    assert transports[0].requests[1] == b"@12345?WA01\r"

    await manager.close()
    assert transports[0].requests[-1] == b"@12345!V0\r"


@pytest.mark.asyncio
async def test_keyed_v2_rejects_negative_v_reply():
    """Bench probe pcap shows a wrong 16-char key yields `-VC` and no session."""
    factory, transports = make_transport_factory(scripted_replies=[b"\x02@ 12345-VC\r"])
    endpoint = PanelEndpoint(
        host="panel",
        account="12345",
        remote_key="0123456789ABCDEF",
        idle_disconnect_seconds=0.01,
    )
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileKeyedV2(remote_key="0123456789ABCDEF"),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError, match=r"Keyed V2 authentication denied by panel \(-VC\)"):
            await manager.submit(TransactionQueryAreas())
        assert transports[0].requests == [b"@12345!V20123456789ABCDEF\r"]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_keyed_v2_handshake_soft_passes_non_fatal_denial():
    """`-VB` is session-state-driven and lets real command traffic continue."""
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345-VB\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r",
            b"\x02@ 12345+V\r",
        ]
    )
    endpoint = PanelEndpoint(
        host="panel",
        account="12345",
        remote_key="0123456789ABCDEF",
        idle_disconnect_seconds=0.01,
    )
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileKeyedV2(remote_key="0123456789ABCDEF"),
        transport_factory=factory,
    )

    try:
        transaction = await manager.execute("?WA01", label="area_status")
        assert transaction.response == b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r"
        assert transports[0].requests[0] == b"@12345!V20123456789ABCDEF\r"
        assert transports[0].requests[1] == b"@12345?WA01\r"
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_keyed_v2_handshake_rejects_unknown_denial():
    """Keyed V2 shares the V2 auth gate; only `-VB` is soft, all others fatal."""
    factory, transports = make_transport_factory(scripted_replies=[b"\x02@ 12345-VA\r"])
    endpoint = PanelEndpoint(host="panel", account="12345")
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileKeyedV2(remote_key="0123456789ABCDEF"),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError, match=r"Keyed V2 authentication denied by panel \(-VA\)"):
            await manager.execute("?WA01")
        assert transports[0].requests == [b"@12345!V20123456789ABCDEF\r"]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_v31_manager_executes_wrapped_wa_transaction():
    auth_reply = encode_wrapped_reply(" 12345", "+V3213 X150")
    query_reply = encode_wrapped_reply(" 12345", "*WA01NNNNPERIMETER\x1e--")
    close_reply = b"\x02@ 12345+V\r"
    factory, transports = make_transport_factory(
        scripted_replies=[auth_reply, query_reply, close_reply]
    )
    endpoint = PanelEndpoint(
        host="panel",
        account="12345",
        v31_compare_material="",
        idle_disconnect_seconds=0.01,
    )
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileV31(),
        transport_factory=factory,
    )

    transaction = await manager.submit(TransactionQueryAreas())

    assert transaction.session_mode is SessionMode.V31
    assert transaction.response == b"@ 12345*WA01NNNNPERIMETER\x1e--\r"
    assert transaction.wire_response == query_reply
    assert transaction.parsed_response is not None
    assert transaction.parsed_response.areas[0].name == "PERIMETER"
    assert transports[0].requests[0] == b"@12345" + build_v31_auth_body("").encode("ascii") + b"\r"
    assert transports[0].requests[1] == encode_account_v3_frame("12345", "?WA01", " ")

    await manager.close()
    assert transports[0].requests[-1] == encode_account_v3_frame("12345", "!V0", " ")


@pytest.mark.asyncio
async def test_v31_rejects_plain_negative_v_reply():
    """Bench allAuthTest1.pcap shows wrong V31 material yields plaintext `-VC`."""
    factory, transports = make_transport_factory(scripted_replies=[b"\x02@ 12345-VC\r"])
    endpoint = PanelEndpoint(
        host="panel",
        account="12345",
        v31_compare_material="",
        idle_disconnect_seconds=0.01,
    )
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileV31(),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError, match=r"V31 authentication denied by panel \(-VC\)"):
            await manager.submit(TransactionQueryAreas())
        assert transports[0].requests == [
            b"@12345" + build_v31_auth_body("").encode("ascii") + b"\r"
        ]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_v30_manager_executes_wrapped_wa_transaction():
    auth_reply = encode_wrapped_reply(" 12345", "+V3213 X150")
    query_reply = encode_wrapped_reply(" 12345", "*WA01NNNNPERIMETER\x1e--")
    close_reply = b"\x02@ 12345+V\r"
    factory, transports = make_transport_factory(
        scripted_replies=[auth_reply, query_reply, close_reply]
    )
    endpoint = PanelEndpoint(
        host="panel",
        account="12345",
        panel_serial="00172CD2",
        user_code="1234",
        v30_tail4="0000",
        idle_disconnect_seconds=0.01,
    )
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileV30(),
        transport_factory=factory,
    )

    transaction = await manager.submit(TransactionQueryAreas())

    assert transaction.session_mode is SessionMode.V30
    assert transaction.response == b"@ 12345*WA01NNNNPERIMETER\x1e--\r"
    assert transaction.wire_response == query_reply
    assert transaction.parsed_response is not None
    assert transaction.parsed_response.areas[0].number == "01"
    assert transports[0].requests[0] == (
        b"@12345" + build_v30_auth_body("12345", "00172CD2", "1234", "0000").encode("ascii") + b"\r"
    )
    assert transports[0].requests[1] == encode_account_v3_frame("12345", "?WA01", " ")

    await manager.close()
    assert transports[0].requests[-1] == encode_account_v3_frame("12345", "!V0", " ")


@pytest.mark.asyncio
async def test_v30_rejects_plain_negative_v_reply():
    """Bench v30Testing.pcap shows a bad V30 token yields plaintext `-VV`."""
    factory, transports = make_transport_factory(scripted_replies=[b"\x02@ 12345-VV\r"])
    endpoint = PanelEndpoint(
        host="panel",
        account="12345",
        panel_serial="00172CD2",
        user_code="1234",
        v30_tail4="0000",
        idle_disconnect_seconds=0.01,
    )
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileV30(),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError, match=r"V30 authentication denied by panel \(-VV\)"):
            await manager.submit(TransactionQueryAreas())
        assert transports[0].requests == [
            b"@12345" + build_v30_auth_body("12345", "00172CD2", "1234", "0000").encode("ascii") + b"\r"
        ]
    finally:
        await manager.close()
