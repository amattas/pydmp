from __future__ import annotations

from pydmp.transport_sync import DMPTransportSync


class _FakeTransport:
    def __init__(self, host: str, port: int, timeout: float):  # noqa: D401
        self.host, self.port, self.timeout = host, port, timeout
        self.connected = False
        self.sent: list[bytes] = []

    async def connect(self):  # noqa: D401
        self.connected = True

    async def disconnect(self):  # noqa: D401
        self.connected = False

    async def send_and_receive(self, data: bytes) -> bytes:  # noqa: D401
        self.sent.append(bytes(data))
        return b""

    @property
    def is_connected(self) -> bool:  # noqa: D401
        return self.connected


def test_transport_sync_connect_disconnect(monkeypatch):
    # patch the class used internally
    import pydmp.transport_sync as ts

    monkeypatch.setattr(ts, "DMPTransport", _FakeTransport)

    t = DMPTransportSync("h", "1", "KEY", port=2011, timeout=1.0)
    t.connect()
    assert t.is_connected
    # During connect, AUTH should be sent
    assert isinstance(t._transport, _FakeTransport)  # type: ignore[attr-defined]
    assert any(b"!V2" in s for s in t._transport.sent)

    t.disconnect()
    # DISCONNECT should be sent
    assert any(b"!V0" in s for s in t._transport.sent)
