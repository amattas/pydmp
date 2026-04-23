import pytest

from pydmp.core import (
    CommandSessionManager,
    CorePanelClient,
    PanelEndpoint,
    SessionHandshakeError,
    SessionMode,
    SessionProfileSecureS,
    TransactionQueryAreas,
    TransactionQueryLockoutCode,
    TransactionQueryZones,
)
from pydmp.core.framing import format_account_frame
from pydmp.core.secure_s import (
    SECURE_S_FRAME_TYPE_DATA,
    SECURE_S_FRAME_TYPE_SETUP_REPLY,
    SECURE_S_PREFIX,
    build_secure_s_frame,
    build_secure_s_setup_frame,
    next_secure_s_send_sequence,
    parse_secure_s_frame,
)


class FakeTransport:
    def __init__(self, endpoint, scripted_replies=None):
        self.endpoint = endpoint
        self._scripted_replies = list(scripted_replies or [])
        self.is_connected = False
        self.requests = []
        self.disconnect_calls = 0

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.disconnect_calls += 1
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


@pytest.mark.asyncio
async def test_secure_s_manager_executes_queries_and_tracks_sequences():
    passphrase = "1234123412341234"
    endpoint = PanelEndpoint(host="panel", account="12345", passphrase=passphrase)

    server_setup_seq = 0xC4F0
    setup_reply = build_secure_s_frame(
        passphrase,
        seq=server_setup_seq,
        ack=7,
        frame_type=SECURE_S_FRAME_TYPE_SETUP_REPLY,
        payload=b"",
    )

    zz_payload = b"\x02@ 12345*ZZ00000\r\x00"
    zz_reply = build_secure_s_frame(
        passphrase,
        seq=0xC4F7,
        ack=0x0018,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=zz_payload,
    )
    zz_reply_frame = parse_secure_s_frame(passphrase, zz_reply)

    wa_payload = b"\x02@ 12345*WA01NNNNPERIMETER\x1e--\r\x00"
    wa_reply = build_secure_s_frame(
        passphrase,
        seq=0xC50A,
        ack=0x002B,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=wa_payload,
    )

    factory, transports = make_transport_factory(
        scripted_replies=[setup_reply, zz_reply, wa_reply]
    )
    manager = CommandSessionManager(
        endpoint=endpoint,
        session_profile=SessionProfileSecureS(),
        transport_factory=factory,
    )

    try:
        lockout_transaction = await manager.submit(TransactionQueryLockoutCode())
        area_transaction = await manager.submit(TransactionQueryAreas())

        assert lockout_transaction.session_mode is SessionMode.SECURE_S
        assert lockout_transaction.response == zz_payload
        assert lockout_transaction.parsed_response.code == "00000"

        assert area_transaction.session_mode is SessionMode.SECURE_S
        assert area_transaction.response == wa_payload
        assert area_transaction.parsed_response.areas[0].number == "01"
        assert area_transaction.parsed_response.areas[0].name == "PERIMETER"

        assert transports[0].requests[0] == build_secure_s_setup_frame(passphrase, seq=0, ack=0)

        first_data_request = build_secure_s_frame(
            passphrase,
            seq=7,
            ack=(server_setup_seq + 7) & 0xFFFF,
            frame_type=SECURE_S_FRAME_TYPE_DATA,
            payload=format_account_frame(endpoint.normalized_account, "?ZZ"),
        )
        assert transports[0].requests[1] == first_data_request

        second_data_request = build_secure_s_frame(
            passphrase,
            seq=next_secure_s_send_sequence(7, 7 + len(format_account_frame(endpoint.normalized_account, "?ZZ"))),
            ack=(zz_reply_frame.seq + zz_reply_frame.logical_length) & 0xFFFF,
            frame_type=SECURE_S_FRAME_TYPE_DATA,
            payload=format_account_frame(endpoint.normalized_account, "?WA01"),
        )
        assert transports[0].requests[2] == second_data_request
    finally:
        await manager.close()

    assert transports[0].disconnect_calls >= 1


@pytest.mark.asyncio
async def test_secure_s_setup_rejects_bare_prefix_reply():
    factory, transports = make_transport_factory(scripted_replies=[SECURE_S_PREFIX])
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="12345", passphrase="1234123412341234"),
        session_profile=SessionProfileSecureS(),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError):
            await manager.submit(TransactionQueryLockoutCode())
        assert transports[0].requests[0] == build_secure_s_setup_frame("1234123412341234")
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_secure_s_setup_rejects_wrong_frame_type():
    passphrase = "1234123412341234"
    reply_with_wrong_type = build_secure_s_frame(
        passphrase,
        seq=0xC4F0,
        ack=7,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=b"",
    )
    factory, _transports = make_transport_factory(scripted_replies=[reply_with_wrong_type])
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="12345", passphrase=passphrase),
        session_profile=SessionProfileSecureS(),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError, match="wrong frame type"):
            await manager.submit(TransactionQueryLockoutCode())
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_secure_s_setup_rejects_ack_mismatch():
    passphrase = "1234123412341234"
    reply_with_bad_ack = build_secure_s_frame(
        passphrase,
        seq=0xC4F0,
        ack=0x0042,
        frame_type=SECURE_S_FRAME_TYPE_SETUP_REPLY,
        payload=b"",
    )
    factory, _transports = make_transport_factory(scripted_replies=[reply_with_bad_ack])
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="12345", passphrase=passphrase),
        session_profile=SessionProfileSecureS(),
        transport_factory=factory,
    )

    try:
        with pytest.raises(SessionHandshakeError, match=r"ACK mismatch: got 0x0042, expected 0x0007"):
            await manager.submit(TransactionQueryLockoutCode())
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_core_panel_client_query_wa_over_secure_s():
    passphrase = "1234123412341234"
    setup_reply = build_secure_s_frame(
        passphrase,
        seq=0xC4F0,
        ack=7,
        frame_type=SECURE_S_FRAME_TYPE_SETUP_REPLY,
        payload=b"",
    )
    wa_reply = build_secure_s_frame(
        passphrase,
        seq=0xC4F7,
        ack=0x0013,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e--\r\x00",
    )
    factory, transports = make_transport_factory(scripted_replies=[setup_reply, wa_reply])
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", passphrase=passphrase),
        session_profile=SessionProfileSecureS(),
        transport_factory=factory,
    )

    try:
        reply = await client.query_wa()
        assert [area.number for area in reply.areas] == ["01", "02"]
        assert [area.name for area in reply.areas] == ["PERIMETER", "INTERIOR"]
        assert transports[0].requests[0] == build_secure_s_setup_frame(passphrase)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_core_panel_client_query_zones_over_secure_s_tracks_each_exchange():
    passphrase = "1234123412341234"
    endpoint = PanelEndpoint(host="panel", account="12345", passphrase=passphrase)

    setup_reply = build_secure_s_frame(
        passphrase,
        seq=0x1000,
        ack=7,
        frame_type=SECURE_S_FRAME_TYPE_SETUP_REPLY,
        payload=b"",
    )

    wa_payload = b"\x02@ 12345*WA01NNNNPERIMETER\x1e02NNNNINTERIOR\x1e--\r\x00"
    wa_reply = build_secure_s_frame(
        passphrase,
        seq=0x1010,
        ack=0x001A,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=wa_payload,
    )
    wa_reply_frame = parse_secure_s_frame(passphrase, wa_reply)

    wb1_payload = b"\x02@ 12345*WBL009NFIRE9\x1eA001DPERIMETER\x1eL001NDOOR1\x1e-\r\x00"
    wb1_reply = build_secure_s_frame(
        passphrase,
        seq=0x1030,
        ack=0x0031,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=wb1_payload,
    )
    wb1_reply_frame = parse_secure_s_frame(passphrase, wb1_reply)

    wb1_terminal_payload = b"\x02@ 12345*WB-\r\x00"
    wb1_terminal_reply = build_secure_s_frame(
        passphrase,
        seq=0x1050,
        ack=0x0042,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=wb1_terminal_payload,
    )
    wb1_terminal_reply_frame = parse_secure_s_frame(passphrase, wb1_terminal_reply)

    wb2_payload = b"\x02@ 12345*WBL009NFIRE9\x1eA002DINTERIOR\x1eL002NWINDOW1\x1e-\r\x00"
    wb2_reply = build_secure_s_frame(
        passphrase,
        seq=0x1070,
        ack=0x0059,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=wb2_payload,
    )
    wb2_reply_frame = parse_secure_s_frame(passphrase, wb2_reply)

    wb2_terminal_reply = build_secure_s_frame(
        passphrase,
        seq=0x1090,
        ack=0x006A,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=b"\x02@ 12345*WB-\r\x00",
    )

    factory, transports = make_transport_factory(
        scripted_replies=[
            setup_reply,
            wa_reply,
            wb1_reply,
            wb1_terminal_reply,
            wb2_reply,
            wb2_terminal_reply,
        ]
    )
    client = CorePanelClient(
        endpoint,
        session_profile=SessionProfileSecureS(),
        transport_factory=factory,
    )

    try:
        reply = await client.manager.submit(TransactionQueryZones())
        assert [area.number for area in reply.parsed_response.areas] == ["01", "02"]
        assert [(zone.number, zone.area_number, zone.name) for zone in reply.parsed_response.zones] == [
            ("001", "01", "DOOR1"),
            ("002", "02", "WINDOW1"),
            ("009", "00", "FIRE9"),
        ]

        expected_requests = [
            build_secure_s_setup_frame(passphrase),
            build_secure_s_frame(
                passphrase,
                seq=7,
                ack=0x1007,
                frame_type=SECURE_S_FRAME_TYPE_DATA,
                payload=format_account_frame(endpoint.normalized_account, "?WA01"),
            ),
            build_secure_s_frame(
                passphrase,
                seq=0x001A,
                ack=(wa_reply_frame.seq + wa_reply_frame.logical_length) & 0xFFFF,
                frame_type=SECURE_S_FRAME_TYPE_DATA,
                payload=format_account_frame(endpoint.normalized_account, "?WB01Y001"),
            ),
            build_secure_s_frame(
                passphrase,
                seq=0x0031,
                ack=(wb1_reply_frame.seq + wb1_reply_frame.logical_length) & 0xFFFF,
                frame_type=SECURE_S_FRAME_TYPE_DATA,
                payload=format_account_frame(endpoint.normalized_account, "?WB"),
            ),
            build_secure_s_frame(
                passphrase,
                seq=0x0042,
                ack=(wb1_terminal_reply_frame.seq + wb1_terminal_reply_frame.logical_length) & 0xFFFF,
                frame_type=SECURE_S_FRAME_TYPE_DATA,
                payload=format_account_frame(endpoint.normalized_account, "?WB02Y001"),
            ),
            build_secure_s_frame(
                passphrase,
                seq=0x0059,
                ack=(wb2_reply_frame.seq + wb2_reply_frame.logical_length) & 0xFFFF,
                frame_type=SECURE_S_FRAME_TYPE_DATA,
                payload=format_account_frame(endpoint.normalized_account, "?WB"),
            ),
        ]
        assert transports[0].requests == expected_requests
    finally:
        await client.close()
