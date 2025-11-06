"""Async Serial 3 (S3) realtime status server for DMP panels.

This server listens for Serial 3 (Z-frames) pushed by the panel and
invokes registered callbacks with parsed messages.

Notes:
- Configure your DMP panel to connect to this machine/port for realtime
  S3 status (Z-frames). Only one connection is expected.
- The server sends an ACK per message: STX + [5-byte account] + 0x06 + CR.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable

_LOGGER = logging.getLogger(__name__)


@dataclass
class S3Message:
    """Parsed Serial 3 Z-frame."""

    account: str
    definition: str  # e.g., 'Za', 'Zq', 'Zc'
    type_code: str | None  # e.g., 'BU', 'OP', 'ON', etc.
    fields: list[str]  # raw fields split on '\\'
    raw: str  # full raw line (ASCII)


Callback = Callable[[S3Message], Awaitable[None] | None]


class DMPStatusServer:
    """Async TCP server for DMP Serial 3 realtime status (Z-frames)."""

    def __init__(self, host: str = "0.0.0.0", port: int = 5001):
        self._host = host
        self._port = port
        self._server: asyncio.base_events.Server | None = None
        self._callbacks: set[Callback] = set()

    def register_callback(self, cb: Callback) -> None:
        self._callbacks.add(cb)

    def remove_callback(self, cb: Callback) -> None:
        self._callbacks.discard(cb)

    async def start(self) -> None:
        if self._server is not None:
            return
        loop = asyncio.get_running_loop()
        self._server = await asyncio.start_server(self._handle_client, self._host, self._port)
        sockets = ", ".join(str(s.getsockname()) for s in (self._server.sockets or []))
        _LOGGER.info("S3 status server listening on %s", sockets)
        # Do not await serve_forever; let caller manage lifecycle

    async def stop(self) -> None:
        server = self._server
        self._server = None
        if server is None:
            return
        _LOGGER.info("Stopping S3 status server")
        server.close()
        await server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        _LOGGER.info("S3 status connection from %s", peer)
        buf = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buf += chunk
                _LOGGER.debug("[s3] recv chunk %d bytes", len(chunk))
                # Process complete frames terminated by CR (\r)
                while b"\r" in buf:
                    line, buf = buf.split(b"\r", 1)
                    if not line:
                        continue
                    await self._process_line(line, writer)
        except Exception as e:
            _LOGGER.warning("Status connection error from %s: %s", peer, e)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            _LOGGER.info("S3 status connection closed: %s", peer)

    async def _process_line(self, line: bytes, writer: asyncio.StreamWriter) -> None:
        """Parse one ASCII line and send ACK if possible."""
        # Expected format (common case): STX (0x02) + 5 acct chars + 'Z'...
        account = self._extract_account(line)
        try:
            text = line.decode("utf-8", errors="replace")
        except Exception:
            text = repr(line)

        # Find first 'Z' and extract message body
        z_index = text.find("Z")
        if z_index == -1:
            _LOGGER.debug("Ignoring non-Z line: %s", text)
            return
        z_body = text[z_index:]
        _LOGGER.debug("[s3] line: %r", z_body[:200])

        # Build message
        msg = self._parse_z_body(account, z_body)

        # Send ACK if we have an account
        if account is not None:
            try:
                ack = b"\x02" + account.encode("ascii", errors="ignore") + b"\x06\r"
                writer.write(ack)
                await writer.drain()
                _LOGGER.debug("[s3] sent ACK for account %r", account)
            except Exception as e:
                _LOGGER.debug("Failed to send ACK: %s", e)

        # Dispatch to callbacks
        await self._dispatch(msg)

    async def _dispatch(self, msg: S3Message) -> None:
        for cb in list(self._callbacks):
            try:
                res = cb(msg)
                if asyncio.iscoroutine(res):
                    await res  # type: ignore[func-returns-value]
            except Exception as e:
                _LOGGER.warning("Status callback error: %s", e)

    @staticmethod
    def _extract_account(line: bytes) -> str | None:
        # Try to match STX + 5 ASCII chars before 'Z'
        m = re.search(rb"\x02(.{5})Z", line)
        if m:
            try:
                return m.group(1).decode("ascii", errors="ignore")
            except Exception:
                return None
        return None

    @staticmethod
    def _parse_z_body(account: str | None, z_body: str) -> S3Message:
        # z_body starts with 'Z...'
        fields = z_body.split("\\")
        raw = z_body
        # Definition: first two chars (e.g., 'Za') if available
        definition = z_body[:2] if len(z_body) >= 2 else z_body
        # Event type: look for a field starting with 't '
        type_code: str | None = None
        for part in fields:
            if part.startswith("t ") and len(part) >= 3:
                # token after 't ' until next backslash
                type_code = part[2:].strip().split(" ")[0].strip('"')
                break
        return S3Message(
            account=(account or "").strip(),
            definition=definition,
            type_code=type_code,
            fields=fields,
            raw=raw,
        )
