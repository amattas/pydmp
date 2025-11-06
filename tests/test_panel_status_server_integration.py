import pytest

from pydmp.const.events import DMPEventType
from pydmp.panel import DMPPanel


class _Srv:
    def __init__(self):
        self.cb = None

    def register_callback(self, cb):
        self.cb = cb

    def remove_callback(self, cb):  # noqa: D401
        if self.cb == cb:
            self.cb = None


@pytest.mark.asyncio
async def test_attach_detach_status_server(monkeypatch):
    p = DMPPanel()
    refreshed = {"ok": False}

    async def fake_refresh():
        refreshed["ok"] = True

    monkeypatch.setattr(p, "_refresh_user_cache", fake_refresh)

    # cause parse_s3_message to return an object with desired category
    class _Evt:
        category = DMPEventType.USER_CODES

    monkeypatch.setattr("pydmp.panel.parse_s3_message", lambda msg: _Evt())

    s = _Srv()
    p.attach_status_server(s)
    # invoke callback
    assert s.cb is not None
    await s.cb(object())
    assert refreshed["ok"] is True
    p.detach_status_server(s)
    assert s.cb is None
