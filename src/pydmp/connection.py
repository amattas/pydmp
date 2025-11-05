"""Async TCP connection to DMP panel."""

import asyncio
import logging
from typing import Any

from .const.commands import DMPCommand
from .const.protocol import DEFAULT_PORT, RATE_LIMIT_SECONDS
from .exceptions import (
    DMPAuthenticationError,
    DMPConnectionError,
    DMPTimeoutError,
)
from .protocol import DMPProtocol, StatusResponse

_LOGGER = logging.getLogger(__name__)


class DMPConnection:
    """Async TCP connection to DMP panel."""

    def __init__(
        self,
        host: str,
        account: str,
        remote_key: str,
        port: int = DEFAULT_PORT,
        timeout: float = 10.0,
    ):
        """Initialize connection.

        Args:
            host: Panel IP address or hostname
            account: 5-digit account number
            remote_key: Remote key for authentication
            port: TCP port (default: 2011)
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.account = account
        self.remote_key = remote_key
        self.timeout = timeout

        self.protocol = DMPProtocol(account, remote_key)

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._last_command_time = 0.0

        _LOGGER.debug(f"Connection initialized for {host}:{port}, account {account}")

    @property
    def is_connected(self) -> bool:
        """Check if connection is established."""
        return self._connected and self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Establish connection to panel and authenticate.

        Raises:
            DMPConnectionError: If connection fails
            DMPAuthenticationError: If authentication fails
            DMPTimeoutError: If connection times out
        """
        if self.is_connected:
            _LOGGER.debug("Already connected")
            return

        try:
            _LOGGER.info(f"Connecting to {self.host}:{self.port}...")
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
            self._connected = True
            _LOGGER.info("Connection established")

            # Authenticate
            await self._authenticate()

        except asyncio.TimeoutError as e:
            raise DMPTimeoutError(f"Connection timeout to {self.host}:{self.port}") from e
        except OSError as e:
            raise DMPConnectionError(f"Failed to connect: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from panel gracefully."""
        if not self.is_connected:
            return

        try:
            # Send disconnect command
            _LOGGER.debug("Sending disconnect command")
            disconnect_cmd = self.protocol.encode_command(DMPCommand.DISCONNECT.value)
            await self._send_raw(disconnect_cmd)

        except Exception as e:
            _LOGGER.warning(f"Error during disconnect: {e}")

        finally:
            # Close connection
            if self._writer:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception as e:
                    _LOGGER.warning(f"Error closing connection: {e}")

            self._reader = None
            self._writer = None
            self._connected = False
            _LOGGER.info("Disconnected")

    async def send_command(
        self, command: str, **kwargs: Any
    ) -> str | StatusResponse | None:
        """Send command to panel and return response.

        Args:
            command: Command to send
            **kwargs: Command parameters

        Returns:
            Response from panel (ACK, NAK, StatusResponse, or None)

        Raises:
            DMPConnectionError: If not connected or send fails
        """
        if not self.is_connected:
            raise DMPConnectionError("Not connected to panel")

        # Rate limiting
        await self._rate_limit()

        # Encode command
        encoded = self.protocol.encode_command(command, **kwargs)

        # Send and receive
        await self._send_raw(encoded)
        response = await self._receive()

        # Decode response
        return self.protocol.decode_response(response)

    async def _authenticate(self) -> None:
        """Authenticate with panel.

        Raises:
            DMPAuthenticationError: If authentication fails
        """
        try:
            _LOGGER.debug("Authenticating...")
            auth_cmd = self.protocol.encode_command(DMPCommand.AUTH.value, key=self.remote_key)
            await self._send_raw(auth_cmd)

            # Read response
            response = await self._receive()
            result = self.protocol.decode_response(response)

            # Authentication typically returns None (no specific ACK)
            # Connection staying open is the success indicator
            _LOGGER.info("Authentication successful")

        except Exception as e:
            self._connected = False
            raise DMPAuthenticationError(f"Authentication failed: {e}") from e

    async def _send_raw(self, data: bytes) -> None:
        """Send raw bytes to panel.

        Args:
            data: Bytes to send

        Raises:
            DMPConnectionError: If send fails
        """
        if not self._writer:
            raise DMPConnectionError("Not connected")

        try:
            _LOGGER.debug(f"Sending: {data}")
            self._writer.write(data)
            await self._writer.drain()
            self._last_command_time = asyncio.get_event_loop().time()

        except Exception as e:
            raise DMPConnectionError(f"Failed to send data: {e}") from e

    async def _receive(self) -> bytes:
        """Receive response from panel.

        Returns:
            Response bytes

        Raises:
            DMPConnectionError: If receive fails
        """
        if not self._reader:
            raise DMPConnectionError("Not connected")

        try:
            # Wait a moment for response to arrive
            await asyncio.sleep(RATE_LIMIT_SECONDS)

            # Read all available data
            data = b""
            while True:
                try:
                    chunk = await asyncio.wait_for(self._reader.read(4096), timeout=1.0)
                    if not chunk:
                        break
                    data += chunk
                except asyncio.TimeoutError:
                    # No more data available
                    break

            _LOGGER.debug(f"Received {len(data)} bytes")
            return data

        except Exception as e:
            raise DMPConnectionError(f"Failed to receive data: {e}") from e

    async def _rate_limit(self) -> None:
        """Apply rate limiting between commands."""
        loop = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_command_time
        if elapsed < RATE_LIMIT_SECONDS:
            wait_time = RATE_LIMIT_SECONDS - elapsed
            _LOGGER.debug(f"Rate limiting: waiting {wait_time:.3f}s")
            await asyncio.sleep(wait_time)

    async def __aenter__(self) -> "DMPConnection":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()
