import asyncio

import pytest

from pydmp.const.events import DMPEventType
from pydmp.panel import DMPPanel
from pydmp.protocol import OutputsResponse, OutputStatus


@pytest.mark.asyncio
async def test_disconnect_cleanup_and_send_fail(monkeypatch):
    p = DMPPanel()

    class Conn:
        def __init__(self):
            self.is_connected = True
            self.closed = False

        async def send_and_receive(self, data: bytes):  # noqa: D401
            raise RuntimeError("send fail")

        async def disconnect(self):  # noqa: D401
            self.is_connected = False

    class Proto:
        def encode_command(self, *a, **k):  # noqa: D401
            return b"DISC"

    key = ("h", p.port, "acct")
    import pydmp.panel as panel_mod

    panel_mod._ACTIVE_CONNECTIONS.add(key)
    p._active_key = key
    p._connection = Conn()  # type: ignore[attr-defined]
    p._protocol = Proto()  # type: ignore[attr-defined]

    await p.disconnect()  # should swallow send failure and clear state
    assert p._connection is None and p._protocol is None and p._active_key is None
    assert key not in panel_mod._ACTIVE_CONNECTIONS


@pytest.mark.asyncio
async def test_get_output_invalid_number_and_mode_mapping_t_p(monkeypatch):
    p = DMPPanel()
    with pytest.raises(KeyError):
        await p.get_output(0)

    class _Conn:
        is_connected = True

    p._connection = _Conn()  # type: ignore[attr-defined]

    outs = {
        "001": OutputStatus(number="001", mode="T", name="O1"),
        "002": OutputStatus(number="002", mode="P", name="O2"),
    }

    async def fake_send(self, command: str, **kwargs):
        return OutputsResponse(outputs=outs)

    monkeypatch.setattr(DMPPanel, "_send_command", fake_send)
    await p.update_output_status()
    o1 = await p.get_output(1)
    o2 = await p.get_output(2)
    assert o1._state == "TP" and o2._state == "PL"


@pytest.mark.asyncio
async def test_check_code_negative_paths(monkeypatch):
    p = DMPPanel()

    # Case 1: refresh_if_missing=False returns None without refresh
    p._user_cache_by_code = {}
    p._user_cache_by_pin = {}
    got = await p.check_code("9999", include_pin=True, refresh_if_missing=False)
    assert got is None

    # Case 2: refresh raises exception then None
    async def bad_refresh():  # noqa: D401
        raise RuntimeError("boom")

    monkeypatch.setattr(p, "_refresh_user_cache", bad_refresh)
    got2 = await p.check_code("9999", include_pin=True, refresh_if_missing=True)
    assert got2 is None


def test_attach_status_server_idempotence_and_detach_unknown(monkeypatch):
    p = DMPPanel()
    refreshed = {"count": 0}

    async def refresh():  # noqa: D401
        refreshed["count"] += 1

    monkeypatch.setattr(p, "_refresh_user_cache", refresh)

    class Srv:
        def __init__(self):
            self._cbs = []

        def register_callback(self, cb):
            self._cbs.append(cb)

        def remove_callback(self, cb):
            if cb in self._cbs:
                self._cbs.remove(cb)

    # Patch parser to produce user codes category
    class _Evt:
        category = DMPEventType.USER_CODES

    monkeypatch.setattr("pydmp.panel.parse_s3_message", lambda msg: _Evt())

    s = Srv()
    p.attach_status_server(s)
    p.attach_status_server(s)  # idempotent
    # Trigger callback
    for cb in list(p._status_callbacks.values()):
        asyncio.run(cb(object()))
    assert refreshed["count"] == 1

    # Detach unknown does nothing
    p.detach_status_server(object())
    # Detach registered
    p.detach_status_server(s)
    assert not p._status_callbacks
