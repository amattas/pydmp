import pytest

from pydmp.exceptions import DMPInvalidParameterError, DMPZoneError
from pydmp.zone import Zone, ZoneSync


class _P:
    def __init__(self, reply="ACK"):
        self.reply = reply
        self.updated = False

    async def _send_command(self, *a, **k):
        return self.reply

    async def update_status(self):
        self.updated = True


@pytest.mark.asyncio
async def test_zone_constructor_update_state_restore_nak_and_get_state():
    with pytest.raises(DMPInvalidParameterError):
        Zone(_P(), 0)

    z = Zone(_P(), 5, name="Front", state="N")
    z.update_state("O", name="Door")
    assert z.name == "Door" and z.state == "O"

    # Restore NAK raises
    with pytest.raises(DMPZoneError):
        await Zone(_P(reply="NAK"), 6, name="Back").restore()

    # get_state causes update_status
    p = _P()
    z2 = Zone(p, 7, name="Win")
    await z2.get_state()
    assert p.updated is True


def test_zone_sync_accessors_and_repr():
    class SyncPanel:
        def _run(self, coro):
            import asyncio

            return asyncio.get_event_loop().run_until_complete(coro)

    p = _P()
    z = Zone(p, 10, name="Z10", state="N")
    s = ZoneSync(z, SyncPanel())
    assert s.number == 10 and s.name == "Z10" and s.state == "N"
    assert isinstance(repr(s), str) and "ZoneSync" in repr(s)
