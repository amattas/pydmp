import pytest

from pydmp.panel import DMPPanel


@pytest.mark.asyncio
async def test_get_outputs_creates_defaults_without_connection():
    p = DMPPanel()
    outs = await p.get_outputs()
    # Should create outputs 1-4 by default
    nums = [o.number for o in outs]
    assert nums[:4] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_get_output_invalid_number_raises():
    p = DMPPanel()
    with pytest.raises(KeyError):
        await p.get_output(0)
    with pytest.raises(KeyError):
        await p.get_output(1000)
