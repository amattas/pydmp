"""Async raw transport used by the stateless core.

`PanelTransport` is intentionally small. It owns the TCP socket, rate limits
back-to-back sends, and collects reply bytes according to a completion policy.
Higher layers decide what those bytes mean.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from .errors import SessionClosedError, SessionConnectError, SessionTimeoutError
from .models import CompletionPolicy, PanelEndpoint, ReplyExpectation


class TransportProtocol(Protocol):
    """Transport contract used by the session manager."""

    @property
    def is_connected(self) -> bool:
        """Return True when the socket is open."""

    async def connect(self) -> None:
        """Open the transport."""

    async def disconnect(self) -> None:
        """Close the transport."""

    async def exchange(self, request: bytes, completion: CompletionPolicy) -> bytes:
        """Send a request and return the raw reply bytes."""


class PanelTransport:
    """Async TCP transport with transaction-level reply collection."""

    def __init__(self, endpoint: PanelEndpoint):
        self._endpoint = endpoint
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._send_lock = asyncio.Lock()
        self._last_send_time = 0.0

    @property
    def is_connected(self) -> bool:
        """Return `True` when the underlying writer is still open."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open a TCP connection to the configured panel."""
        if self.is_connected:
            return

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._endpoint.host, self._endpoint.port),
                timeout=self._endpoint.connect_timeout,
            )
        except asyncio.TimeoutError as err:
            raise SessionConnectError(
                f"Connection timeout to {self._endpoint.host}:{self._endpoint.port}"
            ) from err
        except OSError as err:
            raise SessionConnectError(
                f"Failed to connect to {self._endpoint.host}:{self._endpoint.port}: {err}"
            ) from err

        self._last_send_time = 0.0

    async def disconnect(self) -> None:
        """Close the transport if it is open."""
        if self._writer is None:
            self._reader = None
            return

        try:
            self._writer.close()
            await self._writer.wait_closed()
        finally:
            self._reader = None
            self._writer = None

    async def exchange(self, request: bytes, completion: CompletionPolicy) -> bytes:
        """Send one request and collect the reply according to the policy.

        The send lock keeps one request/reply exchange on the wire at a time.
        That makes the transport safe for the manager's queued transaction
        model.
        """
        if not self.is_connected or self._reader is None or self._writer is None:
            raise SessionClosedError("Transport is not connected")

        async with self._send_lock:
            await self._rate_limit()
            self._writer.write(request)
            await self._writer.drain()
            self._last_send_time = asyncio.get_running_loop().time()
            return await self._receive(completion)

    async def _receive(self, completion: CompletionPolicy) -> bytes:
        """Collect reply bytes until the completion policy says to stop."""
        if self._reader is None:
            raise SessionClosedError("Transport is not connected")

        if completion.reply_expectation is ReplyExpectation.NO_REPLY_EXPECTED:
            return b""

        data = b""
        first_timeout = completion.first_reply_timeout
        loop = asyncio.get_running_loop()
        deadline = None if completion.overall_timeout is None else loop.time() + completion.overall_timeout

        try:
            chunk = await asyncio.wait_for(self._reader.read(4096), timeout=first_timeout)
        except asyncio.TimeoutError as err:
            if completion.reply_expectation is ReplyExpectation.REPLY_OPTIONAL:
                return b""
            raise SessionTimeoutError("Timed out waiting for the first reply chunk") from err

        if not chunk:
            if completion.reply_expectation is ReplyExpectation.REPLY_OPTIONAL:
                return b""
            raise SessionClosedError("Socket closed while waiting for reply data")

        data += chunk

        while True:
            # After the first chunk, we keep reading until an inter-frame pause
            # or the overall timeout says the reply is complete enough.
            if deadline is None:
                timeout = completion.inter_frame_timeout
            else:
                timeout = min(completion.inter_frame_timeout, max(0.0, deadline - loop.time()))
                if timeout == 0.0:
                    break

            try:
                chunk = await asyncio.wait_for(self._reader.read(4096), timeout=timeout)
            except asyncio.TimeoutError:
                break

            if not chunk:
                break

            data += chunk

        return data

    async def _rate_limit(self) -> None:
        """Delay the next send if the endpoint has a non-zero rate limit."""
        elapsed = asyncio.get_running_loop().time() - self._last_send_time
        if elapsed >= self._endpoint.rate_limit_seconds:
            return
        await asyncio.sleep(self._endpoint.rate_limit_seconds - elapsed)
