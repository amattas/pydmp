"""Stateless `!E001` sensor-reset transaction and reply parsing."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SessionProtocolError
from .models import Transaction, ack_or_deny


@dataclass(slots=True)
class SensorResetReply:
    """Parsed reply for `!E001`."""

    acknowledged: bool
    detail: str | None


class TransactionSensorReset(Transaction):
    """Run the firmware-backed `!E001` sensor-reset command."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(
            body="!E001",
            completion=ack_or_deny(),
            label="sensor_reset",
            parser=parse_sensor_reset_reply,
        )


def parse_sensor_reset_reply(reply: bytes) -> SensorResetReply:
    """Parse one local panel reply for `!E001`.

    Current notes support only a conservative `E`-family command model:
    - positive replies start with `+E`
    - negative replies start with `-E`
    - any trailing payload is preserved as opaque detail
    """

    positive = b"+E"
    negative = b"-E"

    positive_index = reply.find(positive)
    negative_index = reply.find(negative)

    if negative_index != -1 and (positive_index == -1 or negative_index < positive_index):
        detail = _extract_detail(reply[negative_index + len(negative) :])
        return SensorResetReply(acknowledged=False, detail=detail)

    if positive_index != -1:
        detail = _extract_detail(reply[positive_index + len(positive) :])
        return SensorResetReply(acknowledged=True, detail=detail)

    raise SessionProtocolError("Reply did not contain an E command marker")


def _extract_detail(suffix: bytes) -> str | None:
    """Return any reply detail that follows `+E` or `-E`."""

    cleaned = suffix.replace(b"\x00", b"").replace(b"\r", b"").replace(b"\n", b"")
    if cleaned.startswith(b"\x1e"):
        cleaned = cleaned[1:]
    if not cleaned:
        return None
    return cleaned.decode("ascii", errors="replace")
