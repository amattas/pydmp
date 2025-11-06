import pytest

from pydmp.status_server import DMPStatusServer


@pytest.mark.asyncio
async def test_start_stop_idempotence():
    srv = DMPStatusServer(host="127.0.0.1", port=0)
    await srv.start()
    # Second start is no-op
    await srv.start()
    await srv.stop()
    # Second stop is no-op and should not raise
    await srv.stop()


@pytest.mark.asyncio
async def test_dispatch_handles_coroutines_and_exceptions(caplog):
    srv = DMPStatusServer()
    got = {"ok": False}

    async def good_cb(msg):  # noqa: D401
        got["ok"] = True

    async def bad_cb(msg):  # noqa: D401
        raise RuntimeError("boom")

    srv.register_callback(good_cb)
    srv.register_callback(bad_cb)
    await srv._dispatch(object())
    assert got["ok"] is True
