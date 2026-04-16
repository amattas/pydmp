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


def test_parse_zone_status_page_rejects_missing_marker():
    with pytest.raises(SessionProtocolError):
        parse_zone_status_page(b"\x02@ 12345*WAbad\r\x00")


@pytest.mark.asyncio
async def test_core_panel_client_query_zones_runs_full_snapshot():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e03NNNNA3\x1e--\r\x00",
            b"\x02@ 12345*WBL003NZ3ARMSW\x1eL009NFIRE9\x1eA001DPERIMETER\x1eL001NDOOR1\x1eL002NWINDOW1\x1e-\r\x00",
            b"\x02@ 12345*WBL003NZ3ARMSW\x1eL009NFIRE9\x1eA002DINTERIOR\x1eL005NMOTION1\x1e-\r\x00",
            b"\x02@ 12345*WBL003NZ3ARMSW\x1eL009NFIRE9\x1eA003DA3\x1eL004NVAULT\x1e-\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

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
        assert len(reply.raw_replies) == 4
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345?WA01\r"
        assert transports[0].requests[2] == b"@12345?WB01Y001\r"
        assert transports[0].requests[3] == b"@12345?WB02Y001\r"
        assert transports[0].requests[4] == b"@12345?WB03Y001\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_transaction_query_zones_uses_last_write_wins():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e--\r\x00",
            b"\x02@ 12345*WBL003NZ3ARMSW\x1eA001DPERIMETER\x1eL001NDOOR1\x1e-\r\x00",
            b"\x02@ 12345*WBL003OZ3ARMSW\x1eA002DINTERIOR\x1eL005NMOTION1\x1e-\r\x00",
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
        assert zones["003"].status == "O"
        assert zones["001"].area_number == "01"
        assert zones["005"].area_number == "02"
        assert transaction.wire_requests == [
            b"@12345?WA01\r",
            b"@12345?WB01Y001\r",
            b"@12345?WB02Y001\r",
        ]
    finally:
        await client.close()
