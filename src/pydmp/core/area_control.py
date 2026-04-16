"""Stateless area arm and disarm transactions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .area_status import normalize_area_number
from .errors import SessionProtocolError
from .models import Transaction, ack_or_deny


@dataclass(slots=True)
class AreaControlReply:
    """Parsed reply for an area arm or disarm command."""

    command: str
    acknowledged: bool
    detail: str | None


def normalize_area_list(areas: int | str | Iterable[int | str]) -> str:
    """Return a concatenated 2-digit area list for `!C` and `!O` commands."""
    if isinstance(areas, (int, str)):
        return normalize_area_number(areas)

    normalized = [normalize_area_number(area) for area in areas]
    if not normalized:
        raise ValueError("Area list must not be empty")

    return "".join(normalized)


class TransactionArmAreas(Transaction):
    """Arm one or more areas with `!C`."""

    __slots__ = ("area_numbers", "bypass_faulted", "force_arm", "instant")

    def __init__(
        self,
        areas: int | str | Iterable[int | str],
        *,
        bypass_faulted: bool = True,
        force_arm: bool = False,
        instant: bool = False,
    ) -> None:
        area_numbers = normalize_area_list(areas)
        self.area_numbers = area_numbers
        self.bypass_faulted = bypass_faulted
        self.force_arm = force_arm
        self.instant = instant

        flags = (
            _bool_to_flag(bypass_faulted),
            _bool_to_flag(force_arm),
            _bool_to_flag(instant),
        )
        super().__init__(
            body=f"!C{area_numbers},{''.join(flags)}",
            completion=ack_or_deny(),
            label="arm_areas",
            parser=parse_area_arm_reply,
        )


class TransactionDisarmAreas(Transaction):
    """Disarm one or more areas with `!O`."""

    __slots__ = ("area_numbers",)

    def __init__(self, areas: int | str | Iterable[int | str]) -> None:
        area_numbers = normalize_area_list(areas)
        self.area_numbers = area_numbers
        super().__init__(
            body=f"!O{area_numbers},",
            completion=ack_or_deny(),
            label="disarm_areas",
            parser=parse_area_disarm_reply,
        )


def parse_area_arm_reply(reply: bytes) -> AreaControlReply:
    """Parse one `!C` reply."""
    return _parse_area_control_reply(reply, command="C")


def parse_area_disarm_reply(reply: bytes) -> AreaControlReply:
    """Parse one `!O` reply."""
    return _parse_area_control_reply(reply, command="O")


def _parse_area_control_reply(reply: bytes, *, command: str) -> AreaControlReply:
    """Parse one local panel reply for `!C` or `!O`."""
    positive = f"+{command}".encode("ascii")
    negative = f"-{command}".encode("ascii")

    positive_index = reply.find(positive)
    negative_index = reply.find(negative)

    if positive_index != -1 and (negative_index == -1 or positive_index < negative_index):
        detail = _extract_detail(reply[positive_index + len(positive):])
        return AreaControlReply(command=command, acknowledged=True, detail=detail)

    if negative_index != -1:
        detail = _extract_detail(reply[negative_index + len(negative):])
        return AreaControlReply(command=command, acknowledged=False, detail=detail)

    raise SessionProtocolError(f"Reply did not contain a {command} command marker")


def _extract_detail(suffix: bytes) -> str | None:
    """Return any reply detail that follows the command marker."""
    cleaned = suffix.replace(b"\x00", b"").replace(b"\r", b"").replace(b"\n", b"")
    if cleaned.startswith(b"\x1e"):
        cleaned = cleaned[1:]
    if not cleaned:
        return None
    return cleaned.decode("ascii", errors="replace")


def _bool_to_flag(value: bool) -> str:
    """Return the panel flag character for one boolean arm option."""
    return "Y" if value else "N"
