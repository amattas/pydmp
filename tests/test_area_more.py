import pytest

from pydmp.area import Area, AreaSync
from pydmp.exceptions import DMPAreaError, DMPInvalidParameterError


class _P:
    def __init__(self, reply="ACK"):
        self.reply = reply
        self.updated = False

    async def _send_command(self, *a, **k):
        return self.reply

    async def update_status(self):
        self.updated = True


@pytest.mark.asyncio
async def test_area_constructor_and_update_state_and_get_state():
    p = _P()
    with pytest.raises(DMPInvalidParameterError):
        Area(p, 0)

    a = Area(p, 1, name="A1", state="D")
    a.update_state("A", name="Main")
    assert a.name == "Main" and a.state == "A"

    # get_state triggers panel.update_status
    await a.get_state()
    assert p.updated is True


@pytest.mark.asyncio
async def test_area_arm_disarm_error_paths(monkeypatch):
    p = _P(reply="NAK")
    a = Area(p, 1, name="A1", state="D")

    with pytest.raises(DMPAreaError):
        await a.arm(bypass_faulted=True, force_arm=False, instant=True)

    with pytest.raises(DMPAreaError):
        await a.disarm()


def test_area_sync_accessors_and_repr():
    class SyncPanel:
        def _run(self, coro):
            import asyncio

            return asyncio.get_event_loop().run_until_complete(coro)

    p = _P()
    a = Area(p, 2, name="Two", state="D")
    s = AreaSync(a, SyncPanel())
    assert s.number == 2 and s.name == "Two" and s.state == "D"
    assert isinstance(repr(s), str) and "AreaSync" in repr(s)
