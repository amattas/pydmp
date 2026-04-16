"""Small helpers for parser-facing local panel framing."""

from __future__ import annotations


MESSAGE_PREFIX = b"@"
MESSAGE_TERMINATOR = b"\r"
BLANK_V2_COMPARE = b" " * 16


def coerce_body_bytes(body: bytes | str) -> bytes:
    """Normalize a logical command/query body to bytes."""
    if isinstance(body, bytes):
        result = body
    else:
        result = body.encode("ascii")
    return result.rstrip(MESSAGE_TERMINATOR)


def format_account_frame(account: str, body: bytes | str) -> bytes:
    """Build a parser-facing local frame: `@<acct><body>\\r`."""
    return MESSAGE_PREFIX + account.encode("ascii") + coerce_body_bytes(body) + MESSAGE_TERMINATOR


def has_v_success(reply: bytes) -> bool:
    """Check for a local `+V...` auth success reply."""
    return b"+V" in reply


def has_v_failure(reply: bytes) -> bool:
    """Check for a local `-V...` auth failure reply."""
    return b"-V" in reply
