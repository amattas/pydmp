import pytest

from pydmp.core import (
    CorePanelClient,
    PanelEndpoint,
    SessionProfileBlankV2,
    SessionProtocolError,
    TransactionQueryZoneSettings,
    ZoneSettingsPage,
    ZoneSettingsReply,
    normalize_zone_settings_number,
    parse_zone_settings_page,
    parse_zone_settings_reply,
)


RECORD_001 = (
    b"001EX01YFFFFFFFFNNN---------00-000S-000SA000SA000S1N1N6NNY0000000003NYN4LY---00000N1F--N0000000000DOOR1"
)
RECORD_002 = (
    b"002IN01Y00000000NNN---------00-000S-000SA000SA000S1N1N6NNY0000000003NYN4LY---00000N0F--N0000000000WINDOW1"
)
RECORD_005_UNUSED = (
    b"005UN01N00000000NNN---------00-000S-000S-000S-000S1N1N6NNY0000000003NYN4LN---00000N0F--N0000000000* UNUSED *"
)
RECORD_009 = (
    b"009FI00N00000000NNN---------00-000S-000ST000SA000S1N1N6NNY0000000003NYN4LN---00000N0F--N0000000000FIRE9"
)
RECORD_011 = (
    b"011NT01Y00000000NNN---------00-000S-000SA000SA000S1N1N6NNY0000000003NYN4LN---00000N0F--N3333333333K1"
)
RECORD_500_LIVE = (
    b"500FI00NFF000000NNN--------Y00-000S-000ST000SA000S1N1N6NNN0738531803NNN4LN---00000N0F--N0000000000-NBASEMENT SMOKE"
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


def test_transaction_query_zone_settings_shape():
    transaction = TransactionQueryZoneSettings(7)

    assert transaction.body == "?ZL007"
    assert transaction.label == "query_zone_settings"
    assert transaction.zone_number == "007"
    assert transaction.parser is not None


def test_normalize_zone_settings_number():
    assert normalize_zone_settings_number(1) == "001"
    assert normalize_zone_settings_number("7") == "007"
    assert normalize_zone_settings_number("007") == "007"
    assert normalize_zone_settings_number("?ZL009") == "009"
    assert normalize_zone_settings_number("?Zl009") == "009"

    with pytest.raises(ValueError):
        normalize_zone_settings_number(0)
    with pytest.raises(ValueError):
        normalize_zone_settings_number(1000)
    with pytest.raises(ValueError):
        normalize_zone_settings_number("0A7")


def test_parse_zone_settings_page_decodes_known_direct_record():
    reply = b"\x02@ 12345*ZL" + RECORD_001 + b"\x1e\r\x00"

    page = parse_zone_settings_page(reply)

    assert page == ZoneSettingsPage(
        records=page.records,
        has_terminal_marker=False,
        raw_reply=reply,
    )
    assert page.short_default is False
    assert len(page.records) == 1

    record = page.records[0]
    assert record.number == "001"
    assert record.type_code == "EX"
    assert record.area == "01"
    assert record.flag_07 == "Y"
    assert record.nibble_word_08_0f == "FFFFFFFF"
    assert record.special_word_13_1a == "--------"
    assert record.marker_1b == "-"
    assert record.type_field_1c_1d == "00"
    assert record.disarmed_open_action == "none"
    assert record.disarmed_open_output == "none"
    assert record.disarmed_open_output_mode == "S"
    assert record.disarmed_short_action == "none"
    assert record.disarmed_short_output == "none"
    assert record.disarmed_short_output_mode == "S"
    assert record.armed_open_action == "A"
    assert record.armed_open_output == "none"
    assert record.armed_open_output_mode == "S"
    assert record.armed_short_action == "A"
    assert record.armed_short_output == "none"
    assert record.armed_short_output_mode == "S"
    assert record.entry_delay_number == "1"
    assert record.literal_34 == "1"
    assert record.display_option == "6"
    assert record.reference8 == "00000000"
    assert record.numeric_42 == "0"
    assert record.numeric_43 == "3"
    assert record.pir_pulse_count == "4"
    assert record.pir_sensitivity == "L"
    assert record.flag_54 == "F"
    assert record.type5_flag_55 == "-"
    assert record.slot_56 == "-"
    assert record.reference_mode_57 == "N"
    assert record.reference10 == "0000000000"
    assert record.name == "DOOR1"
    assert record.unused is False


def test_parse_zone_settings_page_handles_lowercase_multi_record_page():
    reply = b"\x02@ 12345*Zl" + RECORD_001 + b"\x1e" + RECORD_002 + b"\x1e---\r\x00"

    page = parse_zone_settings_page(reply)

    assert page.has_terminal_marker is True
    assert page.short_default is False
    assert [record.number for record in page.records] == ["001", "002"]
    assert [record.name for record in page.records] == ["DOOR1", "WINDOW1"]


def test_parse_zone_settings_page_accepts_repeated_trailing_record_separator():
    reply = b"\x02@ 12345*ZL" + RECORD_001 + b"\x1e\x1e\r\x00"

    page = parse_zone_settings_page(reply)

    assert page.has_terminal_marker is False
    assert page.short_default is False
    assert [record.number for record in page.records] == ["001"]


def test_parse_zone_settings_reply_selects_requested_zone_from_page():
    reply = b"\x02@ 12345*Zl" + RECORD_001 + b"\x1e" + RECORD_002 + b"\x1e---\r\x00"

    parsed = parse_zone_settings_reply(reply, requested_zone=2)

    assert parsed.requested_zone == "002"
    assert parsed.found is True
    assert parsed.zone is not None
    assert parsed.zone.number == "002"
    assert parsed.zone.name == "WINDOW1"
    assert [record.number for record in parsed.records] == ["001", "002"]
    assert parsed.has_terminal_marker is True


def test_parse_zone_settings_page_handles_lowercase_skip_ahead_record():
    reply = b"\x02@ 12345*Zl" + RECORD_009 + b"\x1e---\r\x00"

    page = parse_zone_settings_page(reply)

    assert page.has_terminal_marker is True
    assert page.short_default is False
    assert [record.number for record in page.records] == ["009"]
    assert page.records[0].name == "FIRE9"


def test_parse_zone_settings_page_handles_live_fire_record_tail_variant():
    reply = b"\x02@  3734*ZL" + RECORD_500_LIVE + b"\x1e\x1e\r\x00"

    page = parse_zone_settings_page(reply)

    assert page.has_terminal_marker is False
    assert page.short_default is False
    assert [record.number for record in page.records] == ["500"]
    assert page.records[0].name_prefix == "-N"
    assert page.records[0].name == "BASEMENT SMOKE"


def test_parse_zone_settings_reply_handles_lowercase_skip_ahead_not_found():
    reply = b"\x02@ 12345*Zl" + RECORD_009 + b"\x1e---\r\x00"

    parsed = parse_zone_settings_reply(reply, requested_zone=6)

    assert parsed.requested_zone == "006"
    assert parsed.found is False
    assert parsed.short_default is False
    assert parsed.zone is None
    assert [record.number for record in parsed.records] == ["009"]


def test_parse_zone_settings_page_handles_lowercase_short_default():
    reply = b"\x02@ 12345*Zl---\r\x00"

    page = parse_zone_settings_page(reply)

    assert page.records == []
    assert page.has_terminal_marker is True
    assert page.short_default is True


def test_parse_zone_settings_reply_handles_missing_or_unused_rows():
    empty_reply = b"\x02@ 12345*ZL---\r\x00"
    missing = parse_zone_settings_reply(empty_reply, requested_zone=5)

    assert missing == ZoneSettingsReply(
        requested_zone="005",
        zone=None,
        records=[],
        has_terminal_marker=True,
        raw_reply=empty_reply,
    )
    assert missing.found is False
    assert missing.short_default is True

    unused_reply = b"\x02@ 12345*ZL" + RECORD_005_UNUSED + b"\x1e\r\x00"
    unused = parse_zone_settings_reply(unused_reply, requested_zone=5)

    assert unused.found is True
    assert unused.zone is not None
    assert unused.zone.number == "005"
    assert unused.zone.unused is True
    assert unused.zone.name == "* UNUSED *"


def test_parse_zone_settings_reply_handles_live_fire_record_tail_variant():
    reply = b"\x02@  3734*ZL" + RECORD_500_LIVE + b"\x1e\x1e\r\x00"

    parsed = parse_zone_settings_reply(reply, requested_zone=500)

    assert parsed.found is True
    assert parsed.zone is not None
    assert parsed.zone.number == "500"
    assert parsed.zone.name_prefix == "-N"
    assert parsed.zone.name == "BASEMENT SMOKE"


def test_parse_zone_settings_page_accepts_nonzero_reference10_and_keypad_name():
    reply = b"\x02@ 12345*Zl" + RECORD_011 + b"\x1e---\r\x00"

    page = parse_zone_settings_page(reply)

    assert [record.number for record in page.records] == ["011"]
    assert page.records[0].reference10 == "3333333333"
    assert page.records[0].name == "K1"


@pytest.mark.parametrize(
    "reply",
    [
        b"\x02@ 12345*WB" + RECORD_001 + b"\x1e\r\x00",
        b"\x02@ 12345*ZL\r\x00",
        b"\x02@ 12345*ZL" + b"000" + RECORD_001[3:] + b"\x1e\r\x00",
        b"\x02@ 12345*ZL" + RECORD_001[:3] + b"E1" + RECORD_001[5:] + b"\x1e\r\x00",
        b"\x02@ 12345*ZL" + RECORD_001[:5] + b"33" + RECORD_001[7:] + b"\x1e\r\x00",
        b"\x02@ 12345*ZL" + RECORD_001[:8] + b"GFFFFFFF" + RECORD_001[16:] + b"\x1e\r\x00",
        b"\x02@ 12345*ZL" + RECORD_001[:50] + b"5" + RECORD_001[51:] + b"\x1e\r\x00",
        b"\x02@ 12345*ZL" + RECORD_001[:98] + (b"A" * 33) + b"\x1e\r\x00",
        b"\x02@ 12345*Zl" + RECORD_001 + b"\x1e\x1e---\r\x00",
        b"\x02@ 12345*Zl" + RECORD_001 + b"\x1e---\x1e" + RECORD_002 + b"\x1e\r\x00",
        b"\x02@ 12345*Zl" + RECORD_001 + b"\x1e---\x1e\r\x00",
    ],
)
def test_parse_zone_settings_page_rejects_malformed_records(reply):
    with pytest.raises(SessionProtocolError):
        parse_zone_settings_page(reply)


@pytest.mark.asyncio
async def test_core_panel_client_query_zone_settings_sends_one_request_only():
    reply = b"\x02@ 12345*ZL" + RECORD_001 + b"\x1e\r\x00"
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
        parsed = await client.query_zone_settings(1)
        assert isinstance(parsed, ZoneSettingsReply)
        assert parsed.requested_zone == "001"
        assert parsed.found is True
        assert parsed.zone is not None
        assert parsed.zone.name == "DOOR1"
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1:2] == [b"@12345?ZL001\r"]
    finally:
        await client.close()
