"""Synchronous wrapper for DMP connection."""

import asyncio
from typing import Any

from .connection import DMPConnection
from .const.protocol import DEFAULT_PORT
from .protocol import StatusResponse


class DMPConnectionSync:
    """Synchronous wrapper for DMPConnection."""

    def __init__(
        self,
        host: str,
        account: str,
        remote_key: str,
        port: int = DEFAULT_PORT,
        timeout: float = 10.0,
    ):
        """Initialize sync connection.

        Args:
            host: Panel IP address or hostname
            account: 5-digit account number
            remote_key: Remote key for authentication
            port: TCP port (default: 2011)
            timeout: Connection timeout in seconds
        """
        self._connection = DMPConnection(host, account, remote_key, port, timeout)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run(self, coro: Any) -> Any:
        """Run coroutine synchronously."""
        loop = self._get_loop()
        return loop.run_until_complete(coro)

    @property
    def is_connected(self) -> bool:
        """Check if connection is established."""
        return self._connection.is_connected

    def connect(self) -> None:
        """Establish connection to panel and authenticate."""
        self._run(self._connection.connect())

    def disconnect(self) -> None:
        """Disconnect from panel gracefully."""
        self._run(self._connection.disconnect())

    def send_command(
        self,
        command: str,
        encrypt_user_code: bool = False,
        user_code: str | None = None,
        **kwargs: Any,
    ) -> str | StatusResponse | None:
        """Send command to panel and return response.

        Args:
            command: Command to send
            encrypt_user_code: Whether user code should be encrypted
            user_code: User code for encrypted commands
            **kwargs: Command parameters

        Returns:
            Response from panel (ACK, NAK, StatusResponse, or None)
        """
        return self._run(
            self._connection.send_command(
                command, encrypt_user_code=encrypt_user_code, user_code=user_code, **kwargs
            )
        )

    def __enter__(self) -> "DMPConnectionSync":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.disconnect()
