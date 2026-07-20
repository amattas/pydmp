"""Shared test scaffolding for the pydmp test suite."""

from __future__ import annotations

import asyncio
from typing import Any


class FakeReader:
    """Minimal async reader that yields pre-chunked byte payloads."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, n: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class FakeWriter:
    """Minimal async writer that records everything written to it."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def get_extra_info(self, name: str) -> Any:
        return ("127.0.0.1", 0)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        await asyncio.sleep(0)


def frame_with_header(account: bytes, z_body: bytes) -> bytes:
    """Build a real-panel-shaped S3 frame: STX + 6 header bytes + account + body + CR."""
    header = b"\x02\x00\x00\x00\x00\x00\x00"
    return header + account + z_body + b"\r"
