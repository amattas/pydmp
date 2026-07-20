import asyncio

import pytest

from pydmp.const.events import DMPEventType
from pydmp.panel import DMPPanel
from pydmp.protocol import OutputsResponse, OutputStatus
from pydmp.user import UserCode


class _FakeTransport:
    """Minimal stand-in for DMPTransport used by connect()."""

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self._up = True

    @property
    def is_connected(self):
        return self._up

    async def connect(self):
        self._up = True

    async def send_and_receive(self, data):
        return "ACK"

    async def disconnect(self):
        self._up = False


class _FakeProtocol:
    def __init__(self, account, remote_key):
        self.account = account

    def encode_command(self, *a, **k):
        return b"x"


def _install_fake_transport(monkeypatch):
    import pydmp.panel as panel_mod

    monkeypatch.setattr(panel_mod, "DMPTransport", _FakeTransport)
    monkeypatch.setattr(panel_mod, "DMPProtocol", _FakeProtocol)


@pytest.mark.asyncio
async def test_disconnect_releases_guard_after_socket_drop(monkeypatch):
    # PYDMP-001: an unexpected socket drop must not permanently block reconnect.
    import pydmp.panel as panel_mod

    _install_fake_transport(monkeypatch)
    p = DMPPanel()
    await p.connect("1.2.3.4", "00001", "KEY")
    key = ("1.2.3.4", p.port, "00001")
    assert key in panel_mod._ACTIVE_CONNECTIONS

    # Simulate an unexpected drop: transport reports not-connected.
    p._connection._up = False  # type: ignore[attr-defined]
    assert not p.is_connected

    # disconnect() must still release the registration despite the drop.
    await p.disconnect()
    assert key not in panel_mod._ACTIVE_CONNECTIONS
    assert p._active_key is None

    # A subsequent connect() on the same instance succeeds.
    await p.connect("1.2.3.4", "00001", "KEY")
    assert p.is_connected
    await p.disconnect()
    assert key not in panel_mod._ACTIVE_CONNECTIONS


@pytest.mark.asyncio
async def test_reconnect_same_instance_after_drop_without_disconnect(monkeypatch):
    # PYDMP-001: connect() directly after a drop (no disconnect) must succeed;
    # the instance's own stale registration must not block it.
    _install_fake_transport(monkeypatch)
    p = DMPPanel()
    await p.connect("1.2.3.4", "00001", "KEY")

    p._connection._up = False  # type: ignore[attr-defined]  # unexpected drop
    assert not p.is_connected

    await p.connect("1.2.3.4", "00001", "KEY")
    assert p.is_connected
    await p.disconnect()


@pytest.mark.asyncio
async def test_second_live_instance_same_key_rejected(monkeypatch):
    # PYDMP-001: a genuinely different live panel with the same (host, port,
    # account) is still rejected.
    from pydmp.exceptions import DMPConnectionError

    _install_fake_transport(monkeypatch)
    p1 = DMPPanel()
    await p1.connect("1.2.3.4", "00001", "KEY")
    try:
        p2 = DMPPanel()
        with pytest.raises(DMPConnectionError):
            await p2.connect("1.2.3.4", "00001", "KEY")
    finally:
        await p1.disconnect()


def _make_user(code="1234", pin=""):
    return UserCode(
        number="0001",
        code=code,
        pin=pin,
        profiles=("001", "002", "003", "004"),
        temp_date="010125",
        exp_date="0900",
        name="USER",
    )


@pytest.mark.asyncio
async def test_refresh_user_cache_no_empty_window(monkeypatch):
    # PYDMP-006: a concurrent refresh must never expose an emptied cache to
    # check_code; the live dict is only replaced via an atomic swap.
    p = DMPPanel()
    old = _make_user()
    new = _make_user()
    p._user_cache_by_code = {"1234": old}
    p._user_cache_by_pin = {}

    gate = asyncio.Event()

    async def slow_get_user_codes():
        # Mid-refresh the live cache must still expose the old entry
        # (no clear-then-repopulate window).
        assert p._user_cache_by_code.get("1234") is old
        await gate.wait()
        return [new]

    monkeypatch.setattr(p, "get_user_codes", slow_get_user_codes)

    task = asyncio.create_task(p._refresh_user_cache())
    await asyncio.sleep(0)  # let refresh reach the await inside get_user_codes

    # Concurrent reader during the refresh window still resolves the code.
    got = await p.check_code("1234", refresh_if_missing=False)
    assert got is old

    gate.set()
    await task
    assert p._user_cache_by_code["1234"] is new


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
