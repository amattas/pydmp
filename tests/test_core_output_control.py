"""Readable tests for `!Q` output-control commands."""

import pytest

from pydmp.core import (
    CorePanelClient,
    OutputControlMode,
    OutputControlReply,
    PanelEndpoint,
    SessionProfileBlankV2,
    TransactionSetOutput,
    normalize_output_control_mode,
    parse_output_control_reply,
)


class FakeTransport:
    """Tiny scripted transport used to keep these tests focused on output control."""

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


def test_normalize_output_control_mode():
    assert normalize_output_control_mode(OutputControlMode.OFF) == "O"
    assert normalize_output_control_mode("off") == "O"
    assert normalize_output_control_mode("on") == "S"
    assert normalize_output_control_mode("pulse") == "P"
    assert normalize_output_control_mode("momentary") == "M"
    assert normalize_output_control_mode("T") == "T"
    assert normalize_output_control_mode("W") == "W"
    assert normalize_output_control_mode("a") == "a"
    assert normalize_output_control_mode("t") == "t"

    with pytest.raises(ValueError):
        normalize_output_control_mode("")

    with pytest.raises(ValueError):
        normalize_output_control_mode("X")


def test_transaction_set_output_shape():
    numeric = TransactionSetOutput(1, "on")
    namespaced = TransactionSetOutput("?WQD1", "pulse")

    assert numeric.body == "!Q001S"
    assert numeric.label == "set_output"
    assert numeric.selector == "001"
    assert numeric.mode == "S"

    assert namespaced.body == "!QD01P"
    assert namespaced.selector == "D01"
    assert namespaced.mode == "P"

    with pytest.raises(ValueError):
        TransactionSetOutput(0, "off")


def test_parse_output_control_replies():
    assert parse_output_control_reply(b"\x02@ 12345+Q\r\x00") == OutputControlReply(
        selector=None,
        mode=None,
        acknowledged=True,
        detail=None,
    )
    assert parse_output_control_reply(b"\x02@ 12345+!Q\r\x00").acknowledged is True
    assert parse_output_control_reply(b"\x02@ 12345-Q\r\x00") == OutputControlReply(
        selector=None,
        mode=None,
        acknowledged=False,
        detail=None,
    )
    assert parse_output_control_reply(b"\x02@ 12345-!Q\r\x00") == OutputControlReply(
        selector=None,
        mode=None,
        acknowledged=False,
        detail=None,
    )
    assert parse_output_control_reply(b"\x02@ 12345-QV\r\x00") == OutputControlReply(
        selector=None,
        mode=None,
        acknowledged=False,
        detail="QV",
    )
    assert parse_output_control_reply(b"\x02@ 12345-VV\r\x00") == OutputControlReply(
        selector=None,
        mode=None,
        acknowledged=False,
        detail="VV",
    )


@pytest.mark.asyncio
async def test_core_panel_client_set_output_over_blank_v2():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345+Q\r\x00",
            b"\x02@ 12345+Q\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        on_reply = await client.turn_output_on(1)
        pulse_reply = await client.pulse_output("D01")

        assert on_reply == OutputControlReply(
            selector="001",
            mode="S",
            acknowledged=True,
            detail=None,
        )
        assert pulse_reply == OutputControlReply(
            selector="D01",
            mode="P",
            acknowledged=True,
            detail=None,
        )
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345!Q001S\r"
        assert transports[0].requests[2] == b"@12345!QD01P\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_core_panel_client_set_output_accepts_mode_enum():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345+Q\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        reply = await client.set_output(1, OutputControlMode.STEADY)
        assert reply == OutputControlReply(
            selector="001",
            mode="S",
            acknowledged=True,
            detail=None,
        )
        assert transports[0].requests[1] == b"@12345!Q001S\r"
    finally:
        await client.close()
