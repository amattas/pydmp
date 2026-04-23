import pytest

from pydmp.core import (
    AreaSettingsPage,
    AreaSettingsRecord,
    AreaSettingsReply,
    CorePanelClient,
    PanelEndpoint,
    SessionProfileBlankV2,
    SessionProtocolError,
    TransactionQueryAreaSettings,
    normalize_area_settings_number,
    parse_area_settings_page,
    parse_area_settings_reply,
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


def test_transaction_query_area_settings_shape():
    transaction = TransactionQueryAreaSettings(8)

    assert transaction.body == "?Za08"
    assert transaction.label == "query_area_settings"
    assert transaction.area_number == "08"
    assert transaction.parser is not None


def test_normalize_area_settings_number():
    assert normalize_area_settings_number(1) == "01"
    assert normalize_area_settings_number("8") == "08"
    assert normalize_area_settings_number("08") == "08"
    assert normalize_area_settings_number("?Za08") == "08"
    assert normalize_area_settings_number(32) == "32"

    with pytest.raises(ValueError):
        normalize_area_settings_number(0)
    with pytest.raises(ValueError):
        normalize_area_settings_number(33)
    with pytest.raises(ValueError):
        normalize_area_settings_number("0A")


def test_parse_area_settings_page_decodes_known_record_shape():
    reply = b"\x02@ 12345*Za0854321YFY003YYAY004090N005NTSTAREA8\x1e--\r\x00"

    page = parse_area_settings_page(reply)

    assert page == AreaSettingsPage(
        records=[
            AreaSettingsRecord(
                number="08",
                account="54321",
                auto_arm="Y",
                bad_zones="F",
                auto_disarm="Y",
                armed_output="003",
                bank_saf="Y",
                common="Y",
                dual_authority="A",
                arm_first="Y",
                late_output="004",
                late_arm_delay="090",
                oc_reports="N",
                burg_bell_output="005",
                card_plus_pin="N",
                name="TSTAREA8",
            )
        ],
        has_terminal_marker=True,
        raw_reply=reply,
    )


def test_parse_area_settings_page_preserves_leading_spaces_in_name():
    reply = b"\x02@ 12345*Za0812345NBN000NNNN000060Y000Y  AREA8\x1e--\r\x00"

    page = parse_area_settings_page(reply)

    assert page.records[0].name == "  AREA8"


def test_parse_area_settings_reply_selects_requested_area_from_single_page():
    reply = (
        b"\x02@ 12345*Za0112345NBN000NNNN000060Y000YPERIMETER"
        b"\x1e0212345NBN000NNNN000060Y000YINTERIOR\x1e--\r\x00"
    )

    parsed = parse_area_settings_reply(reply, requested_area=2)

    assert parsed.requested_area == "02"
    assert parsed.found is True
    assert parsed.area is not None
    assert parsed.area.number == "02"
    assert parsed.area.name == "INTERIOR"
    assert [record.number for record in parsed.records] == ["01", "02"]


def test_parse_area_settings_reply_handles_inactive_or_missing_area():
    reply = b"\x02@ 12345*Za--\r\x00"

    parsed = parse_area_settings_reply(reply, requested_area=8)

    assert parsed == AreaSettingsReply(
        requested_area="08",
        area=None,
        records=[],
        has_terminal_marker=True,
        raw_reply=reply,
    )
    assert parsed.found is False


@pytest.mark.parametrize(
    "reply",
    [
        b"\x02@ 12345*WA0112345NBN000NNNN000060Y000YPERIMETER\x1e--\r\x00",
        b"\x02@ 12345*Za\r\x00",
        b"\x02@ 12345*Za0012345NBN000NNNN000060Y000YPERIMETER\x1e--\r\x00",
        b"\x02@ 12345*Za3312345NBN000NNNN000060Y000YPERIMETER\x1e--\r\x00",
        b"\x02@ 12345*Za0A12345NBN000NNNN000060Y000YPERIMETER\x1e--\r\x00",
        b"\x02@ 12345*Za0112A45NBN000NNNN000060Y000YPERIMETER\x1e--\r\x00",
        b"\x02@ 12345*Za0112345XBN000NNNN000060Y000YPERIMETER\x1e--\r\x00",
        b"\x02@ 12345*Za0112345NXN000NNNN000060Y000YPERIMETER\x1e--\r\x00",
        b"\x02@ 12345*Za0112345NBN000NNZN000060Y000YPERIMETER\x1e--\r\x00",
        b"\x02@ 12345*Za0112345NBN00ANNNN000060Y000YPERIMETER\x1e--\r\x00",
        b"\x02@ 12345*Za0112345NBN000NNNN000060Y000Y\x1e--\r\x00",
        b"\x02@ 12345*Za0112345NBN000NNNN000060Y000Y" + (b"A" * 33) + b"\x1e--\r\x00",
        b"\x02@ 12345*Za0112345NBN000NNNN000060Y000YPERIMETER\x1e\r\x00",
        b"\x02@ 12345*Za0112345NBN000NNNN000060Y000YPERIMETER\x1e\x1e--\r\x00",
        (
            b"\x02@ 12345*Za0112345NBN000NNNN000060Y000YPERIMETER"
            b"\x1e--\x1e0212345NBN000NNNN000060Y000YINTERIOR\r\x00"
        ),
        (
            b"\x02@ 12345*Za0112345NBN000NNNN000060Y000YA1\x1e"
            b"0212345NBN000NNNN000060Y000YA2\x1e"
            b"0312345NBN000NNNN000060Y000YA3\x1e"
            b"0412345NBN000NNNN000060Y000YA4\x1e"
            b"0512345NBN000NNNN000060Y000YA5\x1e"
            b"0612345NBN000NNNN000060Y000YA6\x1e"
            b"0712345NBN000NNNN000060Y000YA7\x1e--\r\x00"
        ),
        (
            b"\x02@ 12345*Za"
            + b"0112345NBN000NNNN000060Y000Y"
            + (b"A" * 32)
            + b"\x1e0212345NBN000NNNN000060Y000Y"
            + (b"B" * 32)
            + b"\x1e0312345NBN000NNNN000060Y000Y"
            + (b"C" * 32)
            + b"--\r\x00"
        ),
    ],
)
def test_parse_area_settings_page_rejects_malformed_records(reply):
    with pytest.raises(SessionProtocolError):
        parse_area_settings_page(reply)


@pytest.mark.asyncio
async def test_core_panel_client_query_area_settings_sends_one_request_only():
    reply = (
        b"\x02@ 12345*Za0312345NBN000NNNN000060Y000YAREA THREE"
        b"\x1e0412345YFY003YYAY004090N005NAREA FOUR\x1e--\r\x00"
    )
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            reply,
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        parsed = await client.query_area_settings(3)
        assert isinstance(parsed, AreaSettingsReply)
        assert parsed.requested_area == "03"
        assert parsed.found is True
        assert parsed.area is not None
        assert parsed.area.name == "AREA THREE"
        assert [record.number for record in parsed.records] == ["03", "04"]
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1:2] == [b"@12345?Za03\r"]
    finally:
        await client.close()
