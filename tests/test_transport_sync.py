from __future__ import annotations

from typing import Any

from pydmp.transport_sync import DMPTransportSync


class _FakeTransport:
    def __init__(self, host: str, port: int, timeout: float, fail_send: bool = False) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.connected = False
        self.sent: list[bytes] = []
        self.calls: list[bytes] = []
        self._fail_send = fail_send

    async def connect(self) -> None:  # noqa: D401
        self.connected = True

    async def disconnect(self) -> None:  # noqa: D401
        self.connected = False

    async def send_and_receive(self, data: bytes) -> bytes:  # noqa: D401
        self.sent.append(bytes(data))
        self.calls.append(bytes(data))
        if self._fail_send:
            raise RuntimeError("fail")
        return b""

    @property
    def is_connected(self) -> bool:  # noqa: D401
        return self.connected


def test_transport_sync_connect_disconnect(monkeypatch: Any) -> None:
    # patch the class used internally
    import pydmp.transport_sync as ts

    monkeypatch.setattr(ts, "DMPTransport", _FakeTransport)

    t = DMPTransportSync("h", "1", "KEY", port=2011, timeout=1.0)
    t.connect()
    assert t.is_connected
    # During connect, AUTH should be sent
    assert isinstance(t._transport, _FakeTransport)
    assert any(b"!V2" in s for s in t._transport.sent)

    t.disconnect()
    # DISCONNECT should be sent
    assert any(b"!V0" in s for s in t._transport.sent)


def test_sync_disconnect_exception_path_and_context_manager(monkeypatch: Any) -> None:
    import pydmp.transport_sync as ts

    def _make_failing(host: Any, port: Any, timeout: Any) -> Any:
        return _FakeTransport(host, port, timeout, fail_send=True)

    monkeypatch.setattr(ts, "DMPTransport", _make_failing)
    t = DMPTransportSync("h", "1", "KEY")

    # Force exception in send_and_receive during disconnect; should be swallowed
    t.disconnect()
    assert not t.is_connected

    # Context manager calls connect/disconnect without raising (use OK transport)
    class _OkTransport:
        def __init__(self, *a: Any, **k: Any) -> None:
            self.connected = False

        async def connect(self) -> None:  # noqa: D401
            self.connected = True

        async def disconnect(self) -> None:  # noqa: D401
            self.connected = False

        async def send_and_receive(self, data: bytes) -> bytes:  # noqa: D401
            del data
            return b""

        @property
        def is_connected(self) -> bool:  # noqa: D401
            return self.connected

    created: list[_OkTransport] = []
    original_init = _OkTransport.__init__

    def tracking_init(self: _OkTransport, *a: Any, **k: Any) -> None:
        original_init(self, *a, **k)
        created.append(self)

    monkeypatch.setattr(_OkTransport, "__init__", tracking_init)
    monkeypatch.setattr(ts, "DMPTransport", _OkTransport)
    with DMPTransportSync("h", "1", "KEY"):
        assert created and created[0].connected
    assert not created[0].connected


def test_send_command_pass_through(monkeypatch: Any) -> None:
    import pydmp.transport_sync as ts

    class _Proto:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def encode_command(self, *a: Any, **k: Any) -> bytes:  # noqa: D401
            del a, k
            return b"CMD"

        def decode_response(self, raw: bytes) -> str:  # noqa: D401
            del raw
            return "ACK"

    class _T:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def connect(self) -> None:  # noqa: D401
            return None

        async def disconnect(self) -> None:  # noqa: D401
            return None

        async def send_and_receive(self, data: bytes) -> bytes:  # noqa: D401
            del data
            return b""

        @property
        def is_connected(self) -> bool:  # noqa: D401
            return True

    monkeypatch.setattr(ts, "DMPProtocol", _Proto)
    monkeypatch.setattr(ts, "DMPTransport", _T)

    s = DMPTransportSync("h", "1", "K")
    out = s.send_command("!X", foo=123)
    assert out == "ACK"
