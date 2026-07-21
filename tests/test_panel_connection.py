"""Connect/disconnect/reconnect-guard tests (PYDMP-001)."""

from typing import Any

import pytest

from pydmp.exceptions import DMPConnectionError
from pydmp.panel import DMPPanel
from tests.fakes import cast_protocol, cast_transport, install_fake_transport


class _FakeTransport:
    """Minimal stand-in for DMPTransport used by connect()."""

    def __init__(self, host: Any, port: Any, timeout: Any) -> None:
        self.host = host
        self.port = port
        self._up = True

    @property
    def is_connected(self) -> Any:
        return self._up

    async def connect(self) -> None:
        self._up = True

    async def send_and_receive(self, data: Any) -> Any:
        return "ACK"

    async def disconnect(self) -> None:
        self._up = False


class _FakeProtocol:
    def __init__(self, account: Any, remote_key: Any) -> None:
        self.account = account

    def encode_command(self, *a: Any, **k: Any) -> Any:
        return b"x"


def _install(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_transport(monkeypatch, _FakeTransport, _FakeProtocol)


@pytest.mark.asyncio
async def test_disconnect_releases_guard_after_socket_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    # PYDMP-001: an unexpected socket drop must not permanently block reconnect.
    import pydmp.panel as panel_mod

    _install(monkeypatch)
    p = DMPPanel()
    await p.connect("1.2.3.4", "00001", "KEY")
    key = ("1.2.3.4", p.port, "00001")
    assert key in panel_mod._ACTIVE_CONNECTIONS

    # Simulate an unexpected drop: transport reports not-connected.
    assert isinstance(p._connection, _FakeTransport)
    p._connection._up = False
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
async def test_reconnect_same_instance_after_drop_without_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    # PYDMP-001: connect() directly after a drop (no disconnect) must succeed;
    # the instance's own stale registration must not block it.
    _install(monkeypatch)
    p = DMPPanel()
    await p.connect("1.2.3.4", "00001", "KEY")

    assert isinstance(p._connection, _FakeTransport)
    p._connection._up = False  # unexpected drop
    assert not p.is_connected

    await p.connect("1.2.3.4", "00001", "KEY")
    assert p.is_connected
    await p.disconnect()


@pytest.mark.asyncio
async def test_second_live_instance_same_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # PYDMP-001: a genuinely different live panel with the same (host, port,
    # account) is still rejected.
    _install(monkeypatch)
    p1 = DMPPanel()
    await p1.connect("1.2.3.4", "00001", "KEY")
    try:
        p2 = DMPPanel()
        with pytest.raises(DMPConnectionError):
            await p2.connect("1.2.3.4", "00001", "KEY")
    finally:
        await p1.disconnect()


@pytest.mark.asyncio
async def test_single_connection_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    # test_panel_update_status.py::test_single_connection_guard: an already
    # active connection key (registered out-of-band) blocks a fresh connect().
    from pydmp import panel as panel_mod

    key = ("127.0.0.1", 2011, "00001")
    panel_mod._ACTIVE_CONNECTIONS.add(key)
    try:
        p = DMPPanel()

        # Prevent update_status side effects during this test
        async def no_upd() -> Any:
            return None

        monkeypatch.setattr(DMPPanel, "update_status", lambda self: no_upd())

        with pytest.raises(DMPConnectionError):
            await p.connect("127.0.0.1", "00001", "KEY")
    finally:
        panel_mod._ACTIVE_CONNECTIONS.discard(key)


@pytest.mark.asyncio
async def test_disconnect_cleanup_and_send_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    # test_panel_more.py::test_disconnect_cleanup_and_send_fail: disconnect()
    # must swallow a failing send (e.g. the drop-connection command erroring)
    # and still fully clear connection state.
    import pydmp.panel as panel_mod

    p = DMPPanel()

    class Conn:
        def __init__(self) -> None:
            self.is_connected = True
            self.closed = False

        async def send_and_receive(self, data: bytes) -> bytes:  # noqa: D401
            del data
            raise RuntimeError("send fail")

        async def disconnect(self) -> None:  # noqa: D401
            self.is_connected = False

    class Proto:
        def encode_command(self, *a: Any, **k: Any) -> bytes:  # noqa: D401
            del a, k
            return b"DISC"

    key = ("h", p.port, "acct")
    panel_mod._ACTIVE_CONNECTIONS.add(key)
    p._active_key = key
    p._connection = cast_transport(Conn())
    p._protocol = cast_protocol(Proto())

    await p.disconnect()  # should swallow send failure and clear state
    assert p._connection is None and p._protocol is None and p._active_key is None
    assert key not in panel_mod._ACTIVE_CONNECTIONS
