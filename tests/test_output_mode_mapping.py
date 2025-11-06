import pytest

from pydmp.output import Output


class _Panel:
    async def _send_command(self, cmd, **kwargs):
        return "ACK"


@pytest.mark.asyncio
async def test_output_mode_m_maps_to_on():
    o = Output(_Panel(), 1, "R1")
    await o.set_mode("M")
    assert o.is_on
