import asyncio
import pytest

from pydmp.status_server import DMPStatusServer
from pydmp.status_parser import parse_s3_message
from pydmp.const import DMPEventType, DMPArmingEvent, DMPRealTimeStatusEvent


class FakeWriter:
    def __init__(self):
        self.buffer = bytearray()
        self.closed = False

    def write(self, data: bytes):
        self.buffer.extend(data)

    async def drain(self):
        return None

    def get_extra_info(self, name):
        return ("127.0.0.1", 12345)

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


@pytest.mark.asyncio
async def test_process_line_sends_ack_and_dispatches():
    server = DMPStatusServer()

    # Build a simple Zq (arming status) line with OP (disarmed)
    account = b"    1"  # 5 chars (4 spaces + '1')
    z_body = "Zq\\060\\t \"OP\\a 01\"AREA ONE\\"
    line = b"\x02" + account + z_body.encode("utf-8")

    received = {}

    def cb(msg):
        received["msg"] = msg

    server.register_callback(cb)
    writer = FakeWriter()
    await server._process_line(line, writer)

    # ACK should be: STX + 5 account chars + 0x06 + CR
    assert writer.buffer.startswith(b"\x02" + account + b"\x06\r")
    assert "msg" in received

    evt = parse_s3_message(received["msg"])
    assert evt.category == DMPEventType.ARMING_STATUS
    assert isinstance(evt.code_enum, DMPArmingEvent)
    assert evt.area == "01"


def test_parse_device_status():
    # Simulate Zc device status ON for device v 002
    from pydmp.status_server import S3Message

    fields = [
        "Zc",
        "060",
        't "ON',
        'v 002"OUT2',
    ]
    msg = S3Message(account="00001", definition="Zc", type_code="ON", fields=fields, raw="" )
    evt = parse_s3_message(msg)
    assert evt.category == DMPEventType.REAL_TIME_STATUS
    assert isinstance(evt.code_enum, DMPRealTimeStatusEvent)
    assert evt.device == "002"
    assert evt.device_name == "OUT2"
