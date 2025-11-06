import pytest

from pydmp.const.commands import DMPCommand
from pydmp.panel import DMPPanel


@pytest.mark.asyncio
async def test_arm_areas_flag_variants(monkeypatch):
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]

    recorded = []

    async def fake_send(self, command: str, **kwargs):
        recorded.append((command, dict(kwargs)))
        return "ACK"

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)

    # instant True
    await p.arm_areas([1], bypass_faulted=True, force_arm=False, instant=True)
    # instant False
    await p.arm_areas([2], bypass_faulted=False, force_arm=True, instant=False)
    # instant None
    await p.arm_areas([3], bypass_faulted=False, force_arm=False, instant=None)

    assert recorded[0][0] == DMPCommand.ARM.value
    assert (
        recorded[0][1]["instant"] == "Y"
        and recorded[0][1]["bypass"] == "Y"
        and recorded[0][1]["force"] == "N"
    )
    assert (
        recorded[1][1]["instant"] == "N"
        and recorded[1][1]["bypass"] == "N"
        and recorded[1][1]["force"] == "Y"
    )
    assert (
        recorded[2][1]["instant"] == ""
        and recorded[2][1]["bypass"] == "N"
        and recorded[2][1]["force"] == "N"
    )


@pytest.mark.asyncio
async def test_disarm_nak(monkeypatch):
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]

    async def fake_send(self, command: str, **kwargs):
        return "NAK"

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    with pytest.raises(Exception):
        await p.disarm_areas([1, 2])
