"""Readable tests for area arm and disarm commands."""

import pytest

from pydmp.core import (
    AreaControlReply,
    CommandSessionManager,
    CorePanelClient,
    PanelEndpoint,
    SessionProfileBlankV2,
    TransactionArmAreas,
    TransactionDisarmAreas,
    normalize_area_list,
    parse_area_arm_reply,
    parse_area_disarm_reply,
)


class FakeTransport:
    """Tiny scripted transport used to keep these tests focused on area control."""

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


def test_normalize_area_list():
    assert normalize_area_list(1) == "01"
    assert normalize_area_list("3") == "03"
    assert normalize_area_list([1, "2", 10]) == "010210"
    assert normalize_area_list([1, "01", 2, "2", 1]) == "0102"
    assert normalize_area_list([1, 2, 3]) == "010203"

    with pytest.raises(ValueError):
        normalize_area_list([])

    with pytest.raises(ValueError):
        normalize_area_list(0)

    with pytest.raises(ValueError):
        normalize_area_list([1, 33])


def test_transaction_area_control_shapes():
    arm = TransactionArmAreas([1, "01", 2])
    disarm = TransactionDisarmAreas("3")
    arm_three = TransactionArmAreas([1, 2, 3], bypass_faulted=True, force_arm=False, instant=False)
    disarm_three = TransactionDisarmAreas([1, 2, 3])

    assert arm.body == "!C0102,NNN"
    assert arm.label == "arm_areas"
    assert arm.parser is parse_area_arm_reply
    assert arm.area_numbers == "0102"
    assert arm_three.body == "!C010203,YNN"

    assert disarm.body == "!O03,"
    assert disarm.label == "disarm_areas"
    assert disarm.parser is parse_area_disarm_reply
    assert disarm.area_numbers == "03"
    assert disarm_three.body == "!O010203,"


def test_parse_area_control_replies():
    arm_ok = parse_area_arm_reply(b"\x02@ 12345+C\r\x00")
    arm_ok_bypass = parse_area_arm_reply(b"\x02@ 12345+CB\r\x00")
    arm_deny = parse_area_arm_reply(b"\x02@ 12345-C-V\r\x00")
    disarm_ok = parse_area_disarm_reply(b"\x02@ 12345+O\r\x00")
    disarm_deny = parse_area_disarm_reply(b"\x02@ 12345-OV\r\x00")

    assert arm_ok == AreaControlReply(command="C", acknowledged=True, detail=None)
    assert arm_ok_bypass == AreaControlReply(command="C", acknowledged=True, detail="B")
    assert arm_deny == AreaControlReply(command="C", acknowledged=False, detail="-V")
    assert disarm_ok == AreaControlReply(command="O", acknowledged=True, detail=None)
    assert disarm_deny == AreaControlReply(command="O", acknowledged=False, detail="V")


@pytest.mark.asyncio
async def test_core_panel_client_area_control_over_blank_v2():
    factory, transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345+C\r\x00",
            b"\x02@ 12345+O\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    client = CorePanelClient(PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        arm = await client.arm_areas([1, 2])
        disarm = await client.disarm_areas("01")

        assert arm == AreaControlReply(command="C", acknowledged=True, detail=None)
        assert disarm == AreaControlReply(command="O", acknowledged=True, detail=None)
        assert transports[0].requests[0] == b"@12345!V2                \r"
        assert transports[0].requests[1] == b"@12345!C0102,NNN\r"
        assert transports[0].requests[2] == b"@12345!O01,\r"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manager_applies_area_control_parser_automatically():
    factory, _transports = make_transport_factory(
        scripted_replies=[
            b"\x02@ 12345+V02012345\r",
            b"\x02@ 12345+CB\r\x00",
            b"\x02@ 12345+V\r",
        ]
    )
    manager = CommandSessionManager(endpoint=PanelEndpoint(host="panel", account="12345", idle_disconnect_seconds=0.01), session_profile=SessionProfileBlankV2(), transport_factory=factory)

    try:
        transaction = await manager.submit(TransactionArmAreas(1))
        assert transaction.response == b"\x02@ 12345+CB\r\x00"
        assert transaction.parsed_response == AreaControlReply(
            command="C",
            acknowledged=True,
            detail="B",
        )
        assert transaction.wire_requests == [b"@12345!C01,NNN\r"]
    finally:
        await manager.close()
