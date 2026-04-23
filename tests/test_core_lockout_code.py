"""Readable tests for the small `?ZZ` lockout-code query."""

import pytest

from pydmp.core import (
    CorePanelClient,
    LockoutCodeReply,
    PanelEndpoint,
    SessionProtocolError,
    SessionProfileBlankV2,
    TransactionQueryLockoutCode,
    parse_lockout_code_reply,
)


class FakeTransport:
    """Tiny scripted transport used to keep these tests focused on `?ZZ`."""

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


def test_transaction_query_lockout_code_shape():
    transaction = TransactionQueryLockoutCode()

    assert transaction.body == "?ZZ"
    assert transaction.label == "query_lockout_code"
    assert transaction.parser is parse_lockout_code_reply


def test_parse_lockout_code_reply():
    parsed = parse_lockout_code_reply(b"\x02@ 12345*ZZ00100\r\x00")

    assert isinstance(parsed, LockoutCodeReply)
    assert parsed.code == "00100"
    assert parsed.numeric_value == 100
    assert parsed.is_null is False
    assert parsed.trailing_payload is None


def test_parse_lockout_code_reply_handles_null_and_trailing_payload():
    parsed = parse_lockout_code_reply(b"\x02@ 12345*ZZ00000XYZ\r\x00")

    assert parsed.code == "00000"
    assert parsed.numeric_value == 0
    assert parsed.is_null is True
    assert parsed.trailing_payload == "XYZ"


def test_parse_lockout_code_reply_rejects_missing_marker():
    with pytest.raises(SessionProtocolError):
        parse_lockout_code_reply(b"\x02@ 12345*WA01NNNNPERIMETER\r\x00")


@pytest.mark.asyncio
async def test_core_panel_client_query_lockout_code():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*ZZ00000\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        reply = await client.query_lockout_code()
        assert reply.code == "00000"
        assert reply.numeric_value == 0
        assert reply.is_null is True
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345?ZZ\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manager_applies_zz_parser_automatically():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*ZZ00123\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        transaction = await client.manager.submit(TransactionQueryLockoutCode())
        assert transaction.response == b"\x02@ 12345*ZZ00123\r\x00"
        assert isinstance(transaction.parsed_response, LockoutCodeReply)
        assert transaction.parsed_response.code == "00123"
        assert transaction.parsed_response.numeric_value == 123
        assert transaction.wire_requests == [b"@12345?ZZ\r"]
    finally:
        await client.close()
