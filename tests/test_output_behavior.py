import pytest

from pydmp.exceptions import DMPOutputError
from pydmp.output import Output


class _Panel:
    def __init__(self):
        self.calls = []

    async def _send_command(self, cmd, **kwargs):
        self.calls.append((cmd, dict(kwargs)))
        # return NAK only for mode=P to exercise error in separate test
        return "ACK"


@pytest.mark.asyncio
async def test_output_set_modes_and_toggle():
    p = _Panel()
    o = Output(p, 1, "R1")
    await o.turn_on()
    assert o.is_on
    await o.toggle()
    # previous was ON so toggle calls turn_off
    assert o.is_off


@pytest.mark.asyncio
async def test_output_nak_error():
    class P(_Panel):
        async def _send_command(self, cmd, **kw):
            return "NAK"

    p = P()
    o = Output(p, 1, "R1")
    with pytest.raises(DMPOutputError):
        await o.pulse()
