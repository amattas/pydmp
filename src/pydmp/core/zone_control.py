"""Stateless zone bypass and unbypass transactions."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SessionProtocolError
from .models import Transaction, ack_or_deny


@dataclass(slots=True)
class ZoneControlReply:
    """Parsed reply for a zone bypass or unbypass command."""

    command: str
    acknowledged: bool
    detail: str | None


def normalize_zone_number(zone: int | str) -> str:
    """Return a 3-digit zone number suitable for `!X` / `!Y` commands."""
    zone_text = str(zone).strip()
    if not zone_text.isdigit():
        raise ValueError(f"Zone number must be numeric: {zone!r}")

    zone_number = int(zone_text, 10)
    if not 1 <= zone_number <= 999:
        raise ValueError(f"Zone number must be in 001..999: {zone!r}")

    return f"{zone_number:03d}"


class TransactionBypassZone(Transaction):
    """Bypass one zone with `!X`."""

    __slots__ = ("zone_number",)

    def __init__(self, zone: int | str) -> None:
        zone_number = normalize_zone_number(zone)
        self.zone_number = zone_number
        super().__init__(
            body=f"!X{zone_number}",
            completion=ack_or_deny(),
            label="bypass_zone",
            parser=parse_zone_bypass_reply,
        )


class TransactionUnbypassZone(Transaction):
    """Remove bypass on one zone with `!Y`."""

    __slots__ = ("zone_number",)

    def __init__(self, zone: int | str) -> None:
        zone_number = normalize_zone_number(zone)
        self.zone_number = zone_number
        super().__init__(
            body=f"!Y{zone_number}",
            completion=ack_or_deny(),
            label="unbypass_zone",
            parser=parse_zone_unbypass_reply,
        )


def parse_zone_bypass_reply(reply: bytes) -> ZoneControlReply:
    """Parse one `!X` reply."""
    return _parse_zone_control_reply(reply, command="X")


def parse_zone_unbypass_reply(reply: bytes) -> ZoneControlReply:
    """Parse one `!Y` reply."""
    return _parse_zone_control_reply(reply, command="Y")


def _parse_zone_control_reply(reply: bytes, *, command: str) -> ZoneControlReply:
    """Parse one local panel reply for `!X` or `!Y`."""
    positive = f"+{command}".encode("ascii")
    negative = f"-{command}".encode("ascii")

    positive_index = reply.find(positive)
    negative_index = reply.find(negative)

    if positive_index != -1 and (negative_index == -1 or positive_index < negative_index):
        detail = _extract_detail(reply[positive_index + len(positive):])
        return ZoneControlReply(command=command, acknowledged=True, detail=detail)

    if negative_index != -1:
        detail = _extract_detail(reply[negative_index + len(negative):])
        return ZoneControlReply(command=command, acknowledged=False, detail=detail)

    raise SessionProtocolError(f"Reply did not contain a {command} command marker")


def _extract_detail(suffix: bytes) -> str | None:
    """Return any reply detail that follows `+X`, `-X`, `+Y`, or `-Y`."""
    cleaned = suffix.replace(b"\x00", b"").replace(b"\r", b"").replace(b"\n", b"")
    if cleaned.startswith(b"\x1e"):
        cleaned = cleaned[1:]
    if not cleaned:
        return None
    return cleaned.decode("ascii", errors="replace")
