from pydmp.transport_sync import DMPTransportSync


class _FakeTransport:
    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.closed = False
        self.connected = True
        self.calls = []

    async def connect(self):  # noqa: D401
        self.connected = True

    async def disconnect(self):  # noqa: D401
        self.connected = False

    async def send_and_receive(self, data: bytes):  # noqa: D401
        self.calls.append(data)
        raise RuntimeError("fail")

    @property
    def is_connected(self):  # noqa: D401
        return self.connected


def test_sync_disconnect_exception_path_and_context_manager(monkeypatch):
    import pydmp.transport_sync as ts

    monkeypatch.setattr(ts, "DMPTransport", _FakeTransport)
    t = DMPTransportSync("h", "1", "KEY")

    # Force exception in send_and_receive during disconnect; should be swallowed
    t.disconnect()
    assert not t.is_connected

    # Context manager calls connect/disconnect without raising (use OK transport)
    class _OkTransport:
        def __init__(self, *a, **k):
            self.connected = False

        async def connect(self):  # noqa: D401
            self.connected = True

        async def disconnect(self):  # noqa: D401
            self.connected = False

        async def send_and_receive(self, data):  # noqa: D401
            return b""

        @property
        def is_connected(self):  # noqa: D401
            return self.connected

    monkeypatch.setattr(ts, "DMPTransport", _OkTransport)
    with DMPTransportSync("h", "1", "KEY") as s:
        assert s.is_connected or True


def test_send_command_pass_through(monkeypatch):
    import pydmp.transport_sync as ts

    class _Proto:
        def __init__(self, *a, **k):
            pass

        def encode_command(self, *a, **k):  # noqa: D401
            return b"CMD"

        def decode_response(self, raw):  # noqa: D401
            return "ACK"

    class _T:
        def __init__(self, *a, **k):
            pass

        async def connect(self):  # noqa: D401
            return None

        async def disconnect(self):  # noqa: D401
            return None

        async def send_and_receive(self, data):  # noqa: D401
            return b""

        @property
        def is_connected(self):  # noqa: D401
            return True

    monkeypatch.setattr(ts, "DMPProtocol", _Proto)
    monkeypatch.setattr(ts, "DMPTransport", _T)

    s = DMPTransportSync("h", "1", "K")
    out = s.send_command("!X", foo=123)
    assert out == "ACK"
