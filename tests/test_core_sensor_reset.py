import pytest

from pydmp.core import (
    CommandSessionManager,
    CorePanelClient,
    PanelEndpoint,
    SensorResetReply,
    SessionProfileBlankV2,
    TransactionSensorReset,
    parse_sensor_reset_reply,
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


def test_transaction_sensor_reset_shape():
    transaction = TransactionSensorReset()

    assert transaction.body == "!E001"
    assert transaction.label == "sensor_reset"
    assert transaction.parser is parse_sensor_reset_reply


def test_parse_sensor_reset_reply():
    assert parse_sensor_reset_reply(b"\x02@ 12345+E\r\x00") == SensorResetReply(
        acknowledged=True,
        detail=None,
    )
    assert parse_sensor_reset_reply(b"\x02@ 12345-E\r\x00") == SensorResetReply(
        acknowledged=False,
        detail=None,
    )
    assert parse_sensor_reset_reply(b"\x02@ 12345-Ei06C87\r\x00") == SensorResetReply(
        acknowledged=False,
        detail="i06C87",
    )
    assert parse_sensor_reset_reply(b"\x02@ 12345+Ec18674\r\x00") == SensorResetReply(
        acknowledged=True,
        detail="c18674",
    )


@pytest.mark.asyncio
async def test_core_panel_client_sensor_reset():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345+E\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(
        PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        reply = await client.sensor_reset()
        assert reply == SensorResetReply(acknowledged=True, detail=None)
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345!E001\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manager_sensor_reset_parses_negative_reply():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345-Ez\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(
        endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01),
        session_profile=SessionProfileBlankV2(),
        transport_factory=factory,
    )

    try:
        transaction = await manager.submit(TransactionSensorReset())
        assert transaction.wire_requests == [b"@12345!E001\r"]
        assert transaction.parsed_response == SensorResetReply(
            acknowledged=False,
            detail="z",
        )
    finally:
        await manager.close()
