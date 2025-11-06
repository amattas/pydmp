"""Async TCP transport to DMP panel (raw bytes I/O only)."""

import asyncio
import logging
from typing import Any

from .const.protocol import DEFAULT_PORT, RATE_LIMIT_SECONDS
from .exceptions import (
    DMPConnectionError,
    DMPTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


class DMPTransport:
    """Async TCP transport to DMP panel.

    This class is responsible only for socket lifecycle, rate limiting, and
    sending/receiving raw bytes. No protocol encoding/decoding occurs here.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._last_command_time = 0.0
        self._send_lock = asyncio.Lock()

        _LOGGER.debug("Transport initialized for %s:%s", host, port)

    @property
    def is_connected(self) -> bool:
        return self._connected and self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Establish TCP connection."""
        if self.is_connected:
            _LOGGER.debug("Already connected")
            return
        try:
            _LOGGER.info("Connecting transport to %s:%s", self.host, self.port)
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
            self._connected = True
            _LOGGER.info("Transport connected")
        except asyncio.TimeoutError as e:
            _LOGGER.error("Transport connection timeout to %s:%s", self.host, self.port)
            raise DMPTimeoutError(f"Connection timeout to {self.host}:{self.port}") from e
        except OSError as e:
            _LOGGER.error("Transport failed to connect: %s", e)
            raise DMPConnectionError(f"Failed to connect: {e}") from e

    async def disconnect(self) -> None:
        """Close TCP connection."""
        if not self.is_connected:
            return
        try:
            if self._writer:
                self._writer.close()
                await self._writer.wait_closed()
        finally:
            self._reader = None
            self._writer = None
            self._connected = False
            _LOGGER.info("Transport disconnected")

    async def send_and_receive(self, data: bytes) -> bytes:
        """Send raw bytes and return accumulated response bytes."""
        if not self.is_connected:
            raise DMPConnectionError("Not connected to panel")

        async with self._send_lock:
            await self._rate_limit()
            await self._send_raw(data)
            return await self._receive()

    async def _send_raw(self, data: bytes) -> None:
        if not self._writer:
            raise DMPConnectionError("Not connected")
        try:
            try:
                _LOGGER.debug(">>> %r", data.decode("utf-8", errors="replace"))
            except Exception:
                _LOGGER.debug(">>> %r", data)
            self._writer.write(data)
            await self._writer.drain()
            self._last_command_time = asyncio.get_event_loop().time()
        except Exception as e:
            _LOGGER.error("Transport send failed: %s", e)
            raise DMPConnectionError(f"Failed to send data: {e}") from e

    async def _receive(self) -> bytes:
        if not self._reader:
            raise DMPConnectionError("Not connected")
        try:
            # Short wait to allow response assembly
            await asyncio.sleep(RATE_LIMIT_SECONDS)
            data = b""
            while True:
                try:
                    chunk = await asyncio.wait_for(self._reader.read(4096), timeout=1.0)
                    if not chunk:
                        break
                    data += chunk
                    try:
                        _LOGGER.debug(
                            "<<< chunk %d bytes: %r",
                            len(chunk),
                            chunk.decode("utf-8", errors="replace"),
                        )
                    except Exception:
                        _LOGGER.debug("<<< chunk %d bytes: %r", len(chunk), chunk)
                except asyncio.TimeoutError:
                    break
            _LOGGER.debug("<<< total %d bytes", len(data))
            return data
        except Exception as e:
            _LOGGER.error("Transport receive failed: %s", e)
            raise DMPConnectionError(f"Failed to receive data: {e}") from e

    async def _rate_limit(self) -> None:
        loop = asyncio.get_event_loop()
        elapsed = loop.time() - self._last_command_time
        if elapsed < RATE_LIMIT_SECONDS:
            wait_time = RATE_LIMIT_SECONDS - elapsed
            _LOGGER.debug("Rate limiting: waiting %.3fs", wait_time)
            await asyncio.sleep(wait_time)

    async def __aenter__(self) -> "DMPTransport":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()
