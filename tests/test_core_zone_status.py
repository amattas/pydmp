"""Readable tests for `?WB` zone parsing and full zone snapshots."""

import pytest

from pydmp.core import (
    CorePanelClient,
    PanelEndpoint,
    SessionProtocolError,
    SessionProfileBlankV2,
    TransactionQueryZones,
    ZoneStatusPage,
    ZoneStatusReply,
    parse_zone_status_page,
)


class FakeTransport:
    """Tiny scripted transport used to keep these tests focused on zone logic."""

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


def test_parse_zone_status_page_assigns_global_and_area_rows():
    reply = (
        b"\x02@ 12345*WBL003NZ3ARMSW\x1eL009NFIRE9\x1e"
        b"A001DPERIMETER\x1eL001NDOOR1\x1eL002NWINDOW1\x1e-\r\x00"
    )

    parsed = parse_zone_status_page(reply)

    assert isinstance(parsed, ZoneStatusPage)
    assert parsed.complete is True
    assert parsed.next_area_number == "01"
    assert [(zone.number, zone.area_number, zone.status, zone.name) for zone in parsed.zones] == [
        ("003", "00", "N", "Z3ARMSW"),
        ("009", "00", "N", "FIRE9"),
        ("001", "01", "N", "DOOR1"),
        ("002", "01", "N", "WINDOW1"),
    ]


def test_parse_zone_status_page_carries_forward_existing_area():
    reply = b"\x02@ 12345*WBL005NMOTION1\x1eL007OZ7\x1e-\r\x00"

    parsed = parse_zone_status_page(reply, current_area_number="02")

    assert parsed.complete is True
    assert parsed.next_area_number == "02"
    assert [(zone.number, zone.area_number, zone.status, zone.name) for zone in parsed.zones] == [
        ("005", "02", "N", "MOTION1"),
        ("007", "02", "O", "Z7"),
    ]


def test_parse_zone_status_page_accepts_closed_zone_status_alphabet():
    reply = (
        b"\x02@ 12345*WB"
        b"L001NNORMAL\x1eL002LLOW\x1eL003OOPEN\x1e"
        b"L004MMISSING\x1eL005SSHORT\x1eL006XBYPASSED\x1e-\r\x00"
    )

    parsed = parse_zone_status_page(reply)

    assert [(zone.number, zone.status, zone.name) for zone in parsed.zones] == [
        ("001", "N", "NORMAL"),
        ("002", "L", "LOW"),
        ("003", "O", "OPEN"),
        ("004", "M", "MISSING"),
        ("005", "S", "SHORT"),
        ("006", "X", "BYPASSED"),
    ]


def test_parse_zone_status_page_accepts_name_length_boundaries():
    one_char_reply = b"\x02@ 12345*WBA001DA\x1eL001NA\x1e-\r\x00"
    max_name = b"A" * 32
    max_char_reply = (
        b"\x02@ 12345*WBA001D" + max_name + b"\x1eL001N" + max_name + b"\x1e-\r\x00"
    )

    one_char = parse_zone_status_page(one_char_reply)
    max_char = parse_zone_status_page(max_char_reply)

    assert one_char.next_area_number == "01"
    assert one_char.zones[0].name == "A"
    assert max_char.next_area_number == "01"
    assert max_char.zones[0].name == "A" * 32


def test_parse_zone_status_page_rejects_missing_marker():
    with pytest.raises(SessionProtocolError):
        parse_zone_status_page(b"\x02@ 12345*WAbad\r\x00")


@pytest.mark.parametrize(
    "reply",
    [
        b"\x02@ 12345*WB\r\x00",
        b"\x02@ 12345*WBL001NDOOR\x1e\x1e-\r\x00",
        b"\x02@ 12345*WB-\x1eL001NDOOR\r\x00",
        b"\x02@ 12345*WBA000DPERIMETER\x1e-\r\x00",
        b"\x02@ 12345*WBA033DPERIMETER\x1e-\r\x00",
        b"\x02@ 12345*WBAX01DPERIMETER\x1e-\r\x00",
        b"\x02@ 12345*WBA001ZPERIMETER\x1e-\r\x00",
        b"\x02@ 12345*WBA001D\x1e-\r\x00",
        b"\x02@ 12345*WBA001D" + (b"A" * 33) + b"\x1e-\r\x00",
        b"\x02@ 12345*WBL000NDOOR\x1e-\r\x00",
        b"\x02@ 12345*WBL00ANDOOR\x1e-\r\x00",
        b"\x02@ 12345*WBL001ZDOOR\x1e-\r\x00",
        b"\x02@ 12345*WBL001N\x1e-\r\x00",
        b"\x02@ 12345*WBL001N" + (b"A" * 33) + b"\x1e-\r\x00",
        b"\x02@ 12345*WBL001N\xff\x1e-\r\x00",
    ],
)
def test_parse_zone_status_page_rejects_malformed_records(reply):
    with pytest.raises(SessionProtocolError):
        parse_zone_status_page(reply)


@pytest.mark.asyncio
async def test_core_panel_client_query_zones_runs_full_snapshot():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e03NNNNA3\x1e--\r\x00",
            b"\x02@ 12345*WBL003NZ3ARMSW\x1eL009NFIRE9\x1eA001DPERIMETER\x1eL001NDOOR1\x1eL002NWINDOW1\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345*WBA002DINTERIOR\x1eL005NMOTION1\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345*WBA003DA3\x1eL004NVAULT\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        reply = await client.query_zones()
        assert isinstance(reply, ZoneStatusReply)
        assert [area.number for area in reply.areas] == ["01", "02", "03"]
        assert [(zone.number, zone.area_number, zone.status, zone.name) for zone in reply.zones] == [
            ("001", "01", "N", "DOOR1"),
            ("002", "01", "N", "WINDOW1"),
            ("003", "00", "N", "Z3ARMSW"),
            ("004", "03", "N", "VAULT"),
            ("005", "02", "N", "MOTION1"),
            ("009", "00", "N", "FIRE9"),
        ]
        assert len(reply.raw_replies) == 7
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345?WA01\r"
        assert transports[0].requests[2] == b"@12345?WB01Y001\r"
        assert transports[0].requests[3] == b"@12345?WB\r"
        assert transports[0].requests[4] == b"@12345?WB02Y001\r"
        assert transports[0].requests[5] == b"@12345?WB\r"
        assert transports[0].requests[6] == b"@12345?WB03Y001\r"
        assert transports[0].requests[7] == b"@12345?WB\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_transaction_query_zones_uses_area_scoped_continuations_for_large_panel():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01YNNNPERIMETER\x1e02NNNNINTERIOR\x1e03NNNNBEDROOMS\x1e--\r\x00",
            (
                b"\x02@ 12345*WBL500NBASEMENT SMOKE\x1eL501NUPSTAIRS SMOKE\x1e"
                b"L523NGARAGE HEAT\x1eA001APERIMETER\x1eL502NFRONT DOOR\x1e"
                b"L503NMUD ROOM\x1eL504NKITCHEN GLASS\x1e-\r\x00"
            ),
            (
                b"\x02@ 12345*WBL505NBASEMENT DOUBLE DOOR\x1eL506NLAUNDRY GLASSBREAK\x1e"
                b"L507NBASE BED GLASSBREAK\x1eL508NLAUNDRY WINDOW\x1e"
                b"L509NBASE BED WINDOW\x1eL510NMUDROOM RIGHT WINDOW\x1e"
                b"L511NMUDROOM LEFT WINDOW\x1e-\r\x00"
            ),
            (
                b"\x02@ 12345*WBL512NKITCHEN WINDOW\x1eL513NUPSTAIRS BATH\x1e"
                b"L514NFRONT BED SIDE WINDOW\x1eL515NFRONT BED LEFT WINDOW\x1e"
                b"L516NFRONT BED RIGHT WINDOW\x1e-\r\x00"
            ),
            (
                b"\x02@ 12345*WBL517NLIVING LEFT WINDOW\x1eL518NLIVING RIGHT WINDOW\x1e"
                b"L519NMASTER WINDOW\x1eL520NGARAGE OHD\x1eL521NGARAGE YARD DOOR\x1e"
                b"L522NGARAGE BACK DOOR\x1e-\r\x00"
            ),
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345*WBL500NBASEMENT SMOKE\x1eL501NUPSTAIRS SMOKE\x1eL523NGARAGE HEAT\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345*WBL500NBASEMENT SMOKE\x1eL501NUPSTAIRS SMOKE\x1eL523NGARAGE HEAT\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        transaction = await client.manager.submit(TransactionQueryZones())
        assert isinstance(transaction.parsed_response, ZoneStatusReply)
        assert transaction.parsed_response.complete is True
        assert [zone.number for zone in transaction.parsed_response.zones] == [
            f"{zone_number:03d}" for zone_number in range(500, 524)
        ]
        assert transaction.wire_requests == [
            b"@12345?WA01\r",
            b"@12345?WB01Y001\r",
            b"@12345?WB\r",
            b"@12345?WB\r",
            b"@12345?WB\r",
            b"@12345?WB\r",
            b"@12345?WB02Y001\r",
            b"@12345?WB\r",
            b"@12345?WB03Y001\r",
            b"@12345?WB\r",
        ]
        assert transports[0].requests[1:] == transaction.wire_requests
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_transaction_query_zones_uses_last_write_wins():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e--\r\x00",
            b"\x02@ 12345*WBL003NZ3ARMSW\x1eA001DPERIMETER\x1eL001NDOOR1\x1e-\r\x00",
            b"\x02@ 12345*WBA001DPERIMETER\x1eL001ODOOR1\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345*WBA002DINTERIOR\x1eL005NMOTION1\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await client.manager.submit(TransactionQueryZones())
        assert isinstance(transaction.parsed_response, ZoneStatusReply)
        zones = {zone.number: zone for zone in transaction.parsed_response.zones}
        assert zones["003"].area_number == "00"
        assert zones["003"].status == "N"
        assert zones["001"].area_number == "01"
        assert zones["001"].status == "O"
        assert zones["005"].area_number == "02"
        assert transaction.wire_requests == [
            b"@12345?WA01\r",
            b"@12345?WB01Y001\r",
            b"@12345?WB\r",
            b"@12345?WB\r",
            b"@12345?WB02Y001\r",
            b"@12345?WB\r",
        ]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_transaction_query_zones_uses_query_areas_paging_for_area_discovery():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\r\x00",
            b"\x02@ 12345*WA03NNNNBEDROOMS\x1e--\r\x00",
            b"\x02@ 12345*WBA001DPERIMETER\x1eL001NDOOR1\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345*WBA002DINTERIOR\x1eL002NWINDOW1\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345*WBA003DBEDROOMS\x1eL003NMOTION1\x1e-\r\x00",
            b"\x02@ 12345*WB-\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await client.manager.submit(TransactionQueryZones())
        assert isinstance(transaction.parsed_response, ZoneStatusReply)
        assert transaction.parsed_response.complete is True
        assert [area.number for area in transaction.parsed_response.areas] == ["01", "02", "03"]
        assert [zone.number for zone in transaction.parsed_response.zones] == ["001", "002", "003"]
        assert transaction.wire_requests == [
            b"@12345?WA01\r",
            b"@12345?WA\r",
            b"@12345?WB01Y001\r",
            b"@12345?WB\r",
            b"@12345?WB02Y001\r",
            b"@12345?WB\r",
            b"@12345?WB03Y001\r",
            b"@12345?WB\r",
        ]
        assert transports[0].requests[1:] == transaction.wire_requests
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_transaction_query_zones_stops_on_repeated_incomplete_wb_page():
    wb_page = b"\x02@ 12345*WBA001DPERIMETER\x1eL001NDOOR1\r\x00"
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r\x00",
            wb_page,
            wb_page,
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await client.manager.submit(TransactionQueryZones())
        assert isinstance(transaction.parsed_response, ZoneStatusReply)
        assert transaction.parsed_response.complete is False
        assert [(zone.number, zone.area_number, zone.status, zone.name) for zone in transaction.parsed_response.zones] == [
            ("001", "01", "N", "DOOR1"),
        ]
        assert transaction.wire_requests == [
            b"@12345?WA01\r",
            b"@12345?WB01Y001\r",
            b"@12345?WB\r",
        ]
        assert len(transaction.parsed_response.raw_replies) == 2
    finally:
        await client.close()
