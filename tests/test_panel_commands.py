import pytest

from pydmp.const.commands import DMPCommand
from pydmp.exceptions import DMPConnectionError
from pydmp.panel import DMPPanel
from pydmp.protocol import UserCode, UserCodesResponse


@pytest.mark.asyncio
async def test_arm_areas_builds_and_handles_nak(monkeypatch):
    sent = {}

    async def fake_send(self, command: str, **kwargs):
        sent["cmd"] = command
        sent.update(kwargs)
        return "NAK"

    p = DMPPanel()

    # fake connection presence
    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]
    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)

    with pytest.raises(DMPConnectionError):
        await p.arm_areas([1, 2], bypass_faulted=True, force_arm=False, instant=True)

    assert sent["cmd"] == DMPCommand.ARM.value
    # areas_concat should be two-digit each
    assert sent["area"] == "0102"
    assert sent["bypass"] == "Y" and sent["force"] == "N" and sent["instant"] == "Y"

    # Successful disarm path
    async def ok_send(self, command: str, **kwargs):
        return "ACK"

    monkeypatch.setattr(DMPPanel, "_send_command", ok_send)
    await p.disarm_areas([3, 4])


@pytest.mark.asyncio
async def test_check_code_refresh(monkeypatch):
    p = DMPPanel()
    p._user_cache_by_code = {}
    p._user_cache_by_pin = {}

    async def fake_refresh():
        u = UserCode(
            number="0001",
            code="1234",
            pin="1111",
            profiles=("001", "002", "003", "004"),
            temp_date="010125",
            exp_date="0900",
            name="USER",
        )
        p._user_cache_by_code = {"1234": u}
        p._user_cache_by_pin = {"1111": u}

    monkeypatch.setattr(p, "_refresh_user_cache", fake_refresh)

    got = await p.check_code("1234", include_pin=True)
    assert got and got.number == "0001"


@pytest.mark.asyncio
async def test_get_user_codes_pagination(monkeypatch):
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]

    # page builder
    def uc(num: str) -> UserCode:
        return UserCode(
            number=num,
            code="1234",
            pin="",
            profiles=("001", "002", "003", "004"),
            temp_date="010125",
            exp_date="0900",
            name=f"U{num}",
        )

    pages = [
        UserCodesResponse(users=[uc("0001")], has_more=True, last_number="0001"),
        UserCodesResponse(users=[uc("0002")], has_more=False, last_number="0002"),
    ]
    state = {"i": 0}

    async def fake_send(self, command: str, **kwargs):
        i = state["i"]
        state["i"] = min(i + 1, len(pages) - 1)
        return pages[i]

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    users = await p.get_user_codes()
    assert [u.number for u in users] == ["0001", "0002"]
