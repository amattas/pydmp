import pytest

from pydmp.exceptions import DMPConnectionError
from pydmp.panel import DMPPanel


@pytest.mark.asyncio
async def test_arm_disarm_invalid_inputs():
    p = DMPPanel()

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]

    with pytest.raises(ValueError):
        await p.arm_areas([])

    with pytest.raises(ValueError):
        await p.disarm_areas([])

    # invalid area number (>99)
    with pytest.raises(ValueError):
        await p.disarm_areas([100])


@pytest.mark.asyncio
async def test_start_keepalive_not_connected():
    p = DMPPanel()
    with pytest.raises(DMPConnectionError):
        await p.start_keepalive(0.1)


@pytest.mark.asyncio
async def test_sensor_reset_not_connected():
    p = DMPPanel()
    with pytest.raises(DMPConnectionError):
        await p.sensor_reset()


@pytest.mark.asyncio
async def test_get_area_missing_raises(monkeypatch):
    p = DMPPanel()

    async def no_update():
        return None

    monkeypatch.setattr(p, "update_status", no_update)

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]
    with pytest.raises(KeyError):
        await p.get_area(99)
