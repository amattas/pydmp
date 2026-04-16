import pytest

from pydmp.core import (
    AreaStatusBlock,
    AreaStatusPage,
    AreaStatusReply,
    CorePanelClient,
    PanelEndpoint,
    SessionProtocolError,
    SessionProfileBlankV2,
    TransactionQueryAreas,
    parse_area_status_block,
    parse_area_status_page,
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


def test_build_query_wa_transactions():
    first = TransactionQueryAreas(1)
    assert first.body == "?WA01"
    assert first.label == "query_areas"
    assert first.parser is None
    assert first.area == "01"

    max_area = TransactionQueryAreas(32)
    assert max_area.body == "?WA32"
    assert max_area.area == "32"


def test_query_wa_transaction_rejects_out_of_range_area_numbers():
    with pytest.raises(ValueError):
        TransactionQueryAreas(0)

    with pytest.raises(ValueError):
        TransactionQueryAreas(33)


def test_parse_area_status_page_handles_many_area_records():
    records = [f"{area:02d}NNNNAREA {area:02d}".encode("ascii") for area in range(1, 17)]
    reply = b"\x02@ 12345*WA" + b"\x1e".join(records + [b"--"]) + b"\r\x00"

    parsed = parse_area_status_page(reply)

    assert parsed.complete is True
    assert len(parsed.areas) == 16
    assert parsed.areas[0].number == "01"
    assert parsed.areas[-1].number == "16"
    assert parsed.areas[-1].name == "AREA 16"


def test_parse_area_status_page_with_complete_first_page():
    reply = b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e03NNNNBEDROOMS\x1e--\r\x00"
    parsed = parse_area_status_page(reply)

    assert parsed.complete is True
    assert [area.number for area in parsed.areas] == ["01", "02", "03"]
    assert [area.arming_state for area in parsed.areas] == ["N", "N", "N"]
    assert [area.status_2 for area in parsed.areas] == ["N", "N", "N"]
    assert [area.status_3 for area in parsed.areas] == ["N", "N", "N"]
    assert [area.status_4 for area in parsed.areas] == ["N", "N", "N"]
    assert [area.name for area in parsed.areas] == ["PERIMETER", "INTERIOR", "BEDROOMS"]
    assert isinstance(parsed.areas[0].status, AreaStatusBlock)
    assert isinstance(parsed, AreaStatusPage)


def test_parse_area_status_block_splits_four_characters():
    status = parse_area_status_block("YNNN")

    assert status.arming_state == "Y"
    assert status.status_2 == "N"
    assert status.status_3 == "N"
    assert status.status_4 == "N"


def test_parse_area_status_block_rejects_wrong_length():
    with pytest.raises(SessionProtocolError):
        parse_area_status_block("NNN")


def test_parse_area_status_page_with_exhausted_continuation():
    reply = b"\x02@ 12345*WA--\r\x00"
    parsed = parse_area_status_page(reply)

    assert parsed.complete is True
    assert parsed.areas == []


def test_parse_area_status_page_rejects_missing_marker():
    with pytest.raises(SessionProtocolError):
        parse_area_status_page(b"\x02@ 12345*WBbad\r\x00")


@pytest.mark.asyncio
async def test_core_panel_client_query_wa():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e03NNNNA3\x1e--\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        reply = await client.query_wa(1)
        assert reply.complete is True
        assert [area.number for area in reply.areas] == ["01", "02", "03"]
        assert [area.arming_state for area in reply.areas] == ["N", "N", "N"]
        assert [area.name for area in reply.areas] == ["PERIMETER", "INTERIOR", "A3"]
        assert len(reply.raw_replies) == 1
        assert reply.raw_replies[0] == b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e03NNNNA3\x1e--\r\x00"
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345?WA01\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manager_applies_wa_parser_automatically():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e03NNNNA3\x1e--\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await client.manager.submit(TransactionQueryAreas(1))
        assert transaction.response is not None
        assert isinstance(transaction.parsed_response, AreaStatusReply)
        assert transaction.parsed_response.complete is True
        assert [area.number for area in transaction.parsed_response.areas] == ["01", "02", "03"]
        assert [area.arming_state for area in transaction.parsed_response.areas] == ["N", "N", "N"]
        assert transaction.wire_requests == [b"@12345?WA01\r"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_transaction_query_areas_pages_until_complete():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e02YNNNINTERIOR\r\x00",
            b"\x02@ 12345*WA03NNNNA3\x1e--\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await client.manager.submit(TransactionQueryAreas(1))
        assert transaction.had_reply is True
        assert transaction.wire_requests == [b"@12345?WA01\r", b"@12345?WA\r"]
        assert len(transaction.responses) == 2
        assert isinstance(transaction.parsed_response, AreaStatusReply)
        assert [area.number for area in transaction.parsed_response.areas] == ["01", "02", "03"]
        assert [area.arming_state for area in transaction.parsed_response.areas] == ["N", "Y", "N"]
        assert len(transaction.parsed_response.raw_replies) == 2
    finally:
        await client.close()
