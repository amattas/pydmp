"""Readable tests for `?WQ` output parsing and output query walks."""

import pytest

from pydmp.core import (
    CommandSessionManager,
    CorePanelClient,
    OutputStatusPage,
    OutputStatusRecord,
    OutputStatusReply,
    PanelEndpoint,
    SessionProtocolError,
    SessionProfileBlankV2,
    TransactionQueryOutputs,
    normalize_output_selector,
    parse_output_status_page,
)


class FakeTransport:
    """Tiny scripted transport used to keep these tests focused on output logic."""

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


def test_transaction_query_outputs_shape():
    transaction = TransactionQueryOutputs()

    assert transaction.body == "?WQ001"
    assert transaction.label == "query_outputs"
    assert transaction.parser is None
    assert transaction.start_selector == "001"
    assert transaction.namespace == "numeric"
    assert transaction.named_only is True

    namespaced = TransactionQueryOutputs(1, namespace="D", named_only=False, max_pages=3)
    assert namespaced.body == "?WQD01"
    assert namespaced.start_selector == "D01"
    assert namespaced.namespace == "D"
    assert namespaced.named_only is False
    assert namespaced.max_pages == 3


def test_normalize_output_selector():
    assert normalize_output_selector(1) == "001"
    assert normalize_output_selector("7") == "007"
    assert normalize_output_selector("099") == "099"
    assert normalize_output_selector("?WQD5") == "D05"
    assert normalize_output_selector("f01") == "F01"
    assert normalize_output_selector("G99") == "G99"

    with pytest.raises(ValueError):
        normalize_output_selector(0)
    with pytest.raises(ValueError):
        normalize_output_selector("D00")
    with pytest.raises(ValueError):
        normalize_output_selector("Q01")


def test_output_status_record_name_helpers():
    named = OutputStatusRecord(selector="001", status="S", name=" Relay One ")
    blank = OutputStatusRecord(selector="002", status="O", name="   ")
    unused = OutputStatusRecord(selector="003", status="O", name=" * UNUSED * ")

    assert named.stripped_name == "Relay One"
    assert named.has_name is True
    assert named.is_unused is False
    assert named.is_named_output is True

    assert blank.stripped_name == ""
    assert blank.has_name is False
    assert blank.is_unused is False
    assert blank.is_named_output is False

    assert unused.stripped_name == "* UNUSED *"
    assert unused.has_name is True
    assert unused.is_unused is True
    assert unused.is_named_output is False


def test_parse_output_status_page_handles_four_char_rows_and_names():
    reply = b"\x02@ 12345*WQ001O\x1e002SRELAY TWO\x1e003P\x1e---\r\x00"

    page = parse_output_status_page(reply)

    assert page == OutputStatusPage(
        records=[
            OutputStatusRecord(selector="001", status="O", name=""),
            OutputStatusRecord(selector="002", status="S", name="RELAY TWO"),
            OutputStatusRecord(selector="003", status="P", name=""),
        ],
        empty_terminal_page=False,
        raw_reply=reply,
    )
    assert page.records[0].namespace == "numeric"
    assert page.records[0].number == 1


def test_parse_output_status_page_handles_d_namespace_and_empty_terminal_page():
    reply = b"\x02@ 12345*WQD01OKEYPAD\x1eD02O* UNUSED *\x1eD17S* UNUSED *\x1e---\r\x00"
    page = parse_output_status_page(reply)

    assert [record.selector for record in page.records] == ["D01", "D02", "D17"]
    assert [record.status for record in page.records] == ["O", "O", "S"]
    assert page.records[0].namespace == "D"
    assert page.records[0].number is None
    assert page.records[0].name == "KEYPAD"

    empty = parse_output_status_page(b"\x02@ 12345*WQ---\r\x00")
    assert empty == OutputStatusPage(records=[], empty_terminal_page=True, raw_reply=empty.raw_reply)


@pytest.mark.parametrize(
    "reply",
    [
        b"\x02@ 12345*WQ\r\x00",
        b"\x02@ 12345*WQ001O\r\x00",
        b"\x02@ 12345*WQ001O\x1e\x1e---\r\x00",
        b"\x02@ 12345*WQ001O\x1e---\x1e002O\r\x00",
        (
            b"\x02@ 12345*WQ001O\x1e002O\x1e003O\x1e004O\x1e005O\x1e006O\x1e500O\x1e501O\x1e502O\x1e503O\x1e504O\x1e505O\x1e---\r\x00"
        ),
    ],
)
def test_parse_output_status_page_rejects_malformed_reply(reply):
    with pytest.raises(SessionProtocolError):
        parse_output_status_page(reply)


@pytest.mark.asyncio
async def test_core_panel_client_query_outputs_uses_explicit_reseeding():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WQ001O\x1e002O\x1e003O\x1e004O\x1e005O\x1e006O\x1e500O\x1e501O\x1e502O\x1e503O\x1e504O\x1e---\r\x00",
            b"\x02@ 12345*WQ505O\x1e506SRELAY 506\x1e---\r\x00",
            b"\x02@ 12345*WQ---\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        reply = await client.query_outputs()
        assert isinstance(reply, OutputStatusReply)
        assert reply.complete is True
        assert reply.namespace == "numeric"
        assert reply.named_only is True
        assert [record.selector for record in reply.records] == [
            "506",
        ]
        assert [record.selector for record in reply.all_records] == [
            "001",
            "002",
            "003",
            "004",
            "005",
            "006",
            "500",
            "501",
            "502",
            "503",
            "504",
            "505",
            "506",
        ]
        assert reply.records[-1].status == "S"
        assert reply.records[-1].name == "RELAY 506"
        assert [record.selector for record in reply.outputs] == ["506"]
        assert [record.selector for record in reply.all_outputs] == [
            "001",
            "002",
            "003",
            "004",
            "005",
            "006",
            "500",
            "501",
            "502",
            "503",
            "504",
            "505",
            "506",
        ]
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1:4] == [
            b"@12345?WQ001\r",
            b"@12345?WQ505\r",
            b"@12345?WQ507\r",
        ]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_core_panel_client_query_outputs_supports_explicit_namespace_and_filter():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WQD01OKEYPAD\x1eD02O* UNUSED *\x1e---\r\x00",
            b"\x02@ 12345*WQ---\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        reply = await client.query_outputs(namespace="D", named_only=False)
        assert isinstance(reply, OutputStatusReply)
        assert reply.namespace == "D"
        assert reply.named_only is False
        assert [record.selector for record in reply.records] == ["D01", "D02"]
        assert transports[0].requests[1:3] == [
            b"@12345?WQD01\r",
            b"@12345?WQD03\r",
        ]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manager_query_outputs_walks_explicit_d_namespace_seed():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            (
                b"\x02@ 12345*WQD01OKPD1\x1eD02OKPD2\x1eD03O* UNUSED *\x1eD04O* UNUSED *\x1eD05O* UNUSED *"
                b"\x1eD06O* UNUSED *\x1eD07O* UNUSED *\x1eD08O* UNUSED *\x1eD17S* UNUSED *\x1eD18S* UNUSED *\x1e---\r\x00"
            ),
            b"\x02@ 12345*WQD19S* UNUSED *\x1eD20S* UNUSED *\x1eD21S* UNUSED *\x1e---\r\x00",
            b"\x02@ 12345*WQ---\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        transaction = await manager.submit(TransactionQueryOutputs("D01"))
        assert isinstance(transaction.parsed_response, OutputStatusReply)
        assert [record.selector for record in transaction.parsed_response.records] == [
            "D01",
            "D02",
        ]
        assert [record.selector for record in transaction.parsed_response.all_records] == [
            "D01",
            "D02",
            "D03",
            "D04",
            "D05",
            "D06",
            "D07",
            "D08",
            "D17",
            "D18",
            "D19",
            "D20",
            "D21",
        ]
        assert transaction.parsed_response.outputs == []
        assert transaction.parsed_response.all_outputs == []
        assert transaction.wire_requests == [
            b"@12345?WQD01\r",
            b"@12345?WQD19\r",
            b"@12345?WQD22\r",
        ]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_manager_query_outputs_numeric_seed_does_not_reseed_into_d_namespace():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WQ593O\x1e594O\x1e599O\x1eD01OKEYPAD\x1eD04O* UNUSED *\x1e---\r\x00",
            b"\x02@ 12345*WQ---\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await manager.submit(
            TransactionQueryOutputs("593", named_only=False)
        )
        assert isinstance(transaction.parsed_response, OutputStatusReply)
        assert [record.selector for record in transaction.parsed_response.records] == [
            "593",
            "594",
            "599",
        ]
        assert [record.selector for record in transaction.parsed_response.all_records] == [
            "593",
            "594",
            "599",
            "D01",
            "D04",
        ]
        assert [record.selector for record in transaction.parsed_response.outputs] == [
            "593",
            "594",
            "599",
        ]
        assert [record.selector for record in transaction.parsed_response.all_outputs] == [
            "593",
            "594",
            "599",
        ]
        assert transaction.wire_requests == [
            b"@12345?WQ593\r",
            b"@12345?WQ600\r",
        ]
    finally:
        await manager.close()
