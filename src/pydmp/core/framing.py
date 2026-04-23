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


def is_v_banner_success(reply: bytes) -> bool:
    """Check for a local `+V` success banner (bare or versioned `+V0..+V3`).

    Older pydmp-style panels reply to `!V2` with a plain `+V` and no version
    digit; bench-213 firmware emits `+V2`. Both are valid V2 auth success.
    The `!V0` teardown ack also produces a bare `+V`, but `close()` never
    parses its reply, so there is no collision in practice.
    """
    idx = reply.find(b"+V")
    if idx < 0:
        return False
    third = reply[idx + 2 : idx + 3]
    if third in (b"0", b"1", b"2", b"3"):
        return True
    return third in (b"", b"\r", b"\n", b" ")


def extract_v_denials(reply: bytes) -> tuple[bytes, ...]:
    """Return every `-V[A-Z]` denial code present in order of appearance.

    The 213 bench firmware pairs each `-V*` code with a distinct auth-lane
    condition, and only some are fatal. A buffered reply may carry more than
    one denial (e.g. a soft code followed by a fatal one); callers decide
    which ones to raise on.
    """
    denials: list[bytes] = []
    search_from = 0
    while True:
        idx = reply.find(b"-V", search_from)
        if idx < 0 or idx + 3 > len(reply):
            break
        third = reply[idx + 2 : idx + 3]
        if b"A" <= third <= b"Z":
            denials.append(reply[idx : idx + 3])
        search_from = idx + 3
    return tuple(denials)
