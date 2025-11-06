import pytest

from pydmp.exceptions import DMPZoneError
from pydmp.zone import Zone


class _Panel:
    def __init__(self, reply):
        self.reply = reply

    async def _send_command(self, cmd, **kwargs):
        return self.reply

    async def update_status(self):
        return None


@pytest.mark.asyncio
async def test_zone_bypass_restore_success():
    z = Zone(_Panel("ACK"), 1, name="Front", state="N")
    await z.bypass()
    await z.restore()


@pytest.mark.asyncio
async def test_zone_bypass_nak_raises():
    z = Zone(_Panel("NAK"), 1, name="Front", state="N")
    with pytest.raises(DMPZoneError):
        await z.bypass()
