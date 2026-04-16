"""Stateless `?WB` transactions and reply parsing."""

from __future__ import annotations

from dataclasses import dataclass

from .area_status import AreaStatusRecord, collect_area_status
from .errors import SessionProtocolError
from .models import CompletionPolicy, Transaction, TransactionRunner, payload_required

ZONE_RECORD_SEPARATOR = b"\x1e"
ZONE_REPLY_PREFIXES = (b"*WB", b"!WB", b"?WB")
ZONE_QUERY_CONTINUATION_BODY = "?WB"
ZONE_GLOBAL_AREA_NUMBER = "00"
ZONE_START_ZONE = "001"
ZONE_EMIT_FLAG = "Y"


@dataclass(slots=True)
class ZoneStatusRecord:
    """One parsed zone record from a `?WB` transaction."""

    number: str
    area_number: str
    status: str
    name: str


@dataclass(slots=True)
class ZoneStatusPage:
    """One parsed `?WB` reply page."""

    zones: list[ZoneStatusRecord]
    complete: bool
    raw_reply: bytes
    next_area_number: str


@dataclass(slots=True)
class ZoneStatusReply:
    """Parsed result of a complete `?WB` zone snapshot transaction."""

    zones: list[ZoneStatusRecord]
    areas: list[AreaStatusRecord]
    complete: bool
    raw_replies: list[bytes]


class TransactionQueryZones(Transaction):
    """Complete full-panel zone snapshot transaction.

    This transaction always discovers areas through `?WA` first, then runs one
    area-scoped `?WB` sweep per discovered area.
    """

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(
            body="?WA01",
            completion=payload_required(),
            label="query_zones",
        )

    async def execute_in_session(
        self,
        exchange: TransactionRunner,
        *,
        session_mode,
        endpoint=None,
    ) -> Transaction:
        del endpoint
        discovered = await collect_area_status(
            self,
            exchange,
            start_area="01",
            session_mode=session_mode,
        )

        raw_replies = list(discovered.raw_replies)
        zones_by_number: dict[str, ZoneStatusRecord] = {}

        for area in discovered.areas:
            sweep = await collect_zone_status_for_area(
                self,
                exchange,
                area_number=area.number,
                session_mode=session_mode,
            )
            raw_replies.extend(sweep.raw_replies)
            for zone in sweep.zones:
                if zone.number in zones_by_number:
                    del zones_by_number[zone.number]
                zones_by_number[zone.number] = zone

        self.parsed_response = ZoneStatusReply(
            zones=sorted(zones_by_number.values(), key=lambda zone: int(zone.number)),
            areas=discovered.areas,
            complete=discovered.complete,
            raw_replies=raw_replies,
        )
        return self


@dataclass(slots=True)
class ZoneStatusCollection:
    """Internal result for one full area-scoped `?WB` sweep."""

    zones: list[ZoneStatusRecord]
    raw_replies: list[bytes]
    complete: bool


async def collect_zone_status_for_area(
    transaction: Transaction,
    exchange: TransactionRunner,
    *,
    area_number: str,
    session_mode,
) -> ZoneStatusCollection:
    """Collect a full paged `?WB` sweep for one discovered area."""
    current_body: bytes | str = f"?WB{area_number}{ZONE_EMIT_FLAG}{ZONE_START_ZONE}"
    current_area_number = ZONE_GLOBAL_AREA_NUMBER
    collected_zones: list[ZoneStatusRecord] = []
    raw_replies: list[bytes] = []
    completion: CompletionPolicy = transaction.completion

    while True:
        exchange_result = await exchange(current_body, completion)
        transaction.record_exchange(exchange_result, session_mode=session_mode)

        if exchange_result.response is None:
            raise SessionProtocolError("Zone query completed without a reply payload")

        page = parse_zone_status_page(
            exchange_result.response,
            current_area_number=current_area_number,
        )
        raw_replies.append(page.raw_reply)
        collected_zones.extend(page.zones)
        current_area_number = page.next_area_number

        if page.complete:
            return ZoneStatusCollection(
                zones=collected_zones,
                raw_replies=raw_replies,
                complete=True,
            )

        current_body = ZONE_QUERY_CONTINUATION_BODY


def parse_zone_status_page(
    reply: bytes,
    *,
    current_area_number: str = ZONE_GLOBAL_AREA_NUMBER,
) -> ZoneStatusPage:
    """Parse one raw panel reply page for the `?WB` family."""
    payload = _extract_zone_payload(reply)
    cleaned = payload.rstrip(b"\r\x00")
    if cleaned == b"-":
        return ZoneStatusPage(
            zones=[],
            complete=True,
            raw_reply=reply,
            next_area_number=current_area_number,
        )

    parts = [part for part in cleaned.split(ZONE_RECORD_SEPARATOR) if part]
    zones: list[ZoneStatusRecord] = []
    complete = False
    next_area_number = current_area_number

    for part in parts:
        if part == b"-":
            complete = True
            continue

        marker = part[:1]
        if marker == b"A":
            next_area_number = _parse_area_anchor(part)
            continue
        if marker == b"L":
            zones.append(_parse_zone_row(part, area_number=next_area_number))
            continue

        raise SessionProtocolError(f"Malformed ?WB record: {part!r}")

    return ZoneStatusPage(
        zones=zones,
        complete=complete,
        raw_reply=reply,
        next_area_number=next_area_number,
    )


def _parse_area_anchor(raw_row: bytes) -> str:
    """Parse one `AxxxSNAME` area anchor row and return the active area."""
    if len(raw_row) < 5:
        raise SessionProtocolError(f"Malformed ?WB area anchor: {raw_row!r}")
    area_number = f"{int(raw_row[1:4].decode('ascii', errors='strict')):02d}"
    _state = raw_row[4:5].decode("ascii", errors="strict")
    _name = raw_row[5:].decode("ascii", errors="replace").strip()
    return area_number


def _parse_zone_row(raw_row: bytes, *, area_number: str) -> ZoneStatusRecord:
    """Parse one `LxxxSNAME` zone row."""
    if len(raw_row) < 5:
        raise SessionProtocolError(f"Malformed ?WB zone row: {raw_row!r}")
    number = raw_row[1:4].decode("ascii", errors="strict")
    status = raw_row[4:5].decode("ascii", errors="strict")
    name = raw_row[5:].decode("ascii", errors="replace").strip()
    return ZoneStatusRecord(
        number=number,
        area_number=area_number,
        status=status,
        name=name,
    )


def _extract_zone_payload(reply: bytes) -> bytes:
    """Extract the body that follows the `*WB`/`!WB`/`?WB` marker."""
    for marker in ZONE_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index + len(marker):]

    raise SessionProtocolError("Reply did not contain a WB marker")
