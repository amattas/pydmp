import pytest

from pydmp.status_server import DMPStatusServer, S3Message

from .fakes import FakeReader, FakeWriter, as_stream_reader, as_stream_writer, frame_with_header


@pytest.mark.asyncio
async def test_start_stop_idempotence() -> None:
    srv = DMPStatusServer(host="127.0.0.1", port=0)
    await srv.start()
    # Second start is no-op
    await srv.start()
    await srv.stop()
    # Second stop is no-op and should not raise
    await srv.stop()


@pytest.mark.asyncio
async def test_handle_client_multiple_lines() -> None:
    srv = DMPStatusServer()
    got: list[S3Message] = []
    srv.register_callback(lambda m: got.append(m))

    account = b"    1"
    line1 = frame_with_header(account, b'Za\\060\\t "BU\\z 001"Z1\\')
    line2 = frame_with_header(account, b'Zq\\060\\t "OP\\a 01"AREA\\')
    reader = FakeReader([line1 + line2, b""])  # both in one chunk
    writer = FakeWriter()

    await srv._handle_client(as_stream_reader(reader), as_stream_writer(writer))

    # Expect two callbacks and two ACK frames
    assert len(got) == 2
    assert writer.buffer.count(b"\x06\r") == 2


@pytest.mark.asyncio
async def test_real_panel_frame_with_header_bytes() -> None:
    """Frames from real panels have 6 header bytes between STX and account."""
    srv = DMPStatusServer()
    got: list[S3Message] = []
    srv.register_callback(lambda m: got.append(m))

    acct = b"00001"
    z_body = b'Zq\\060\\t "CL\\a 001"AREA ONE\\'
    frame = frame_with_header(acct, z_body)
    reader = FakeReader([frame, b""])
    writer = FakeWriter()
    await srv._handle_client(as_stream_reader(reader), as_stream_writer(writer))

    # ACK should contain the correct account
    assert b"\x0200001\x06\r" in writer.buffer
    # Callback should have fired with parsed arming event
    assert len(got) == 1
    assert got[0].account == "00001"
    assert got[0].definition == "Zq"
    assert got[0].type_code == "CL"


@pytest.mark.asyncio
async def test_process_line_sends_ack_and_dispatches() -> None:
    server = DMPStatusServer()

    # Build a simple Zq (arming status) line with OP (disarmed)
    # Real panel format: STX + 6 header bytes + 5 account + Z-body
    account = b"    1"  # 5 chars (4 spaces + '1')
    z_body = 'Zq\\060\\t "OP\\a 01"AREA ONE\\'
    line = frame_with_header(account, z_body.encode("utf-8"))[:-1]  # strip trailing CR

    received: dict[str, S3Message] = {}

    def cb(msg: S3Message) -> None:
        received["msg"] = msg

    server.register_callback(cb)
    writer = FakeWriter()
    await server._process_line(line, as_stream_writer(writer))

    # ACK should be: STX + 5 account chars + 0x06 + CR
    assert writer.buffer.startswith(b"\x02" + account + b"\x06\r")
    assert "msg" in received

    from pydmp.const import DMPArmingEvent, DMPEventType
    from pydmp.status_parser import parse_s3_message

    evt = parse_s3_message(received["msg"])
    assert evt.category == DMPEventType.ARMING_STATUS
    assert isinstance(evt.code_enum, DMPArmingEvent)
    assert evt.area == "01"


@pytest.mark.asyncio
async def test_dispatch_handles_coroutines_and_exceptions(caplog: pytest.LogCaptureFixture) -> None:
    srv = DMPStatusServer()
    got = {"ok": False}

    async def good_cb(msg: S3Message) -> None:  # noqa: D401
        del msg
        got["ok"] = True

    async def bad_cb(msg: S3Message) -> None:  # noqa: D401
        del msg
        raise RuntimeError("boom")

    srv.register_callback(good_cb)
    srv.register_callback(bad_cb)
    await srv._dispatch(S3Message("", "", None, [], ""))
    assert got["ok"] is True


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(
            b"\x02\x00\x00\x00\x00\x00\x00" + b"00001Zq\\...",
            b"00001",
            id="valid",
        ),
        pytest.param(
            b"\x02\x00\x00\x00\x00\x00\x00" + b"    1Zq\\...",
            b"    1",
            id="spaces",
        ),
        pytest.param(
            b"\x02\x00\x00\x00\x00\x00\x00" + b"00001s07keepalive",
            b"00001",
            id="non-z-frame",
        ),
        pytest.param(b"abcdeZ...", None, id="no-stx"),
        pytest.param(b"\x02short", None, id="too-short"),
    ],
)
def test_extract_account(line: bytes, expected: bytes | None) -> None:
    assert DMPStatusServer._extract_account(line) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reader_chunks", "expected_ack_count", "expect_callback", "exact_ack"),
    [
        pytest.param([b"abZq\\...\r", b""], 0, None, None, id="no-account-no-ack"),
        pytest.param(
            [
                frame_with_header(b"00001", b"s07keepalive"),
                b"",
            ],
            1,
            False,
            b"\x0200001\x06\r",
            id="non-z-frame-acked-no-callback",
        ),
        pytest.param(
            [frame_with_header(b"00001", b"Zq\\..."), b""],
            1,
            True,
            None,
            id="single-z-frame-acked-with-callback",
        ),
        pytest.param(
            [
                frame_with_header(b"00001", b"Zq\\...") + frame_with_header(b"00001", b"Za\\..."),
                b"",
            ],
            2,
            True,
            None,
            id="two-z-frames-two-acks",
        ),
    ],
)
async def test_ack_behavior(
    reader_chunks: list[bytes],
    expected_ack_count: int,
    expect_callback: bool | None,
    exact_ack: bytes | None,
) -> None:
    srv = DMPStatusServer()
    got: list[S3Message] = []
    srv.register_callback(lambda m: got.append(m))

    reader = FakeReader(reader_chunks)
    writer = FakeWriter()
    await srv._handle_client(as_stream_reader(reader), as_stream_writer(writer))

    assert writer.buffer.count(b"\x06\r") == expected_ack_count
    if exact_ack is not None:
        assert exact_ack in writer.buffer
    if expect_callback is True:
        assert len(got) >= 1
    elif expect_callback is False:
        assert len(got) == 0
