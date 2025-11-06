"""Synchronous wrapper for DMP transport + protocol (bytes + codec)."""

import asyncio
from typing import Any

from .const.commands import DMPCommand
from .const.protocol import DEFAULT_PORT
from .protocol import DMPProtocol, StatusResponse
from .transport import DMPTransport


class DMPTransportSync:
    """Synchronous wrapper combining DMPTransport and DMPProtocol."""

    def __init__(
        self,
        host: str,
        account: str,
        remote_key: str,
        port: int = DEFAULT_PORT,
        timeout: float = 10.0,
    ):
        """Initialize sync transport."""
        self._transport = DMPTransport(host, port, timeout)
        self._protocol = DMPProtocol(account, remote_key)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run(self, coro: Any) -> Any:
        loop = self._get_loop()
        return loop.run_until_complete(coro)

    @property
    def is_connected(self) -> bool:
        return self._transport.is_connected

    def connect(self) -> None:
        """Establish connection and authenticate."""
        self._run(self._transport.connect())
        auth = self._protocol.encode_command(DMPCommand.AUTH.value, key=self._protocol.remote_key)
        self._run(self._transport.send_and_receive(auth))

    def disconnect(self) -> None:
        """Disconnect gracefully."""
        try:
            disc = self._protocol.encode_command(DMPCommand.DISCONNECT.value)
            self._run(self._transport.send_and_receive(disc))
        except Exception:
            pass
        self._run(self._transport.disconnect())

    def send_command(
        self,
        command: str,
        encrypt_user_code: bool = False,
        user_code: str | None = None,
        **kwargs: Any,
    ) -> str | StatusResponse | None:
        """Send a protocol command and return decoded response."""
        encoded = self._protocol.encode_command(command, **kwargs)
        raw = self._run(self._transport.send_and_receive(encoded))
        return self._protocol.decode_response(raw)

    def __enter__(self) -> "DMPTransportSync":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()


# Back-compat alias
DMPConnectionSync = DMPTransportSync
