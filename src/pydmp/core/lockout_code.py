"""Stateless `?ZZ` transaction and reply parsing."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SessionProtocolError
from .models import Transaction, payload_required

LOCKOUT_CODE_REPLY_PREFIXES = (b"*ZZ", b"!ZZ", b"?ZZ")


@dataclass(slots=True)
class LockoutCodeReply:
    """Parsed result of a `?ZZ` lockout-code query."""

    code: str
    numeric_value: int
    is_null: bool
    trailing_payload: str | None = None


class TransactionQueryLockoutCode(Transaction):
    """Query the programmer lockout code through `?ZZ`."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(
            body="?ZZ",
            completion=payload_required(),
            label="query_lockout_code",
            parser=parse_lockout_code_reply,
        )


def parse_lockout_code_reply(reply: bytes) -> LockoutCodeReply:
    """Parse one raw panel reply for the `?ZZ` family."""
    payload = _extract_lockout_code_payload(reply).rstrip(b"\r\x00")
    if len(payload) < 5:
        raise SessionProtocolError(f"Malformed ?ZZ payload: {payload!r}")

    code = payload[:5].decode("ascii", errors="strict")
    if not code.isdigit():
        raise SessionProtocolError(f"Malformed ?ZZ code field: {code!r}")

    trailing_payload = None
    if len(payload) > 5:
        trailing_payload = payload[5:].decode("ascii", errors="replace")

    numeric_value = int(code, 10)
    return LockoutCodeReply(
        code=code,
        numeric_value=numeric_value,
        is_null=(code == "00000"),
        trailing_payload=trailing_payload or None,
    )


def _extract_lockout_code_payload(reply: bytes) -> bytes:
    """Extract the body that follows the `*ZZ`/`!ZZ`/`?ZZ` marker."""
    for marker in LOCKOUT_CODE_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index + len(marker):]

    raise SessionProtocolError("Reply did not contain a ZZ marker")
