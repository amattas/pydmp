"""Stateless `?WA` transactions and reply parsing."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SessionProtocolError
from .models import (
    CompletionPolicy,
    Transaction,
    TransactionRunner,
    payload_required,
)

AREA_RECORD_SEPARATOR = b"\x1e"
AREA_REPLY_PREFIXES = (b"*WA", b"!WA", b"?WA")
AREA_QUERY_CONTINUATION_BODY = "?WA"


@dataclass(slots=True)
class AreaStatusBlock:
    """One parsed 4-character `?WA` status block.

    Current source material supports only one confident interpretation:
    - `arming_state`

    The remaining three positions are kept split out, but deliberately unnamed
    beyond their position until captures or RE support something stronger.
    """

    arming_state: str
    status_2: str
    status_3: str
    status_4: str


@dataclass(slots=True)
class AreaStatusRecord:
    """One parsed area record from a `?WA` reply."""

    number: str
    status: AreaStatusBlock
    name: str

    @property
    def arming_state(self) -> str:
        """Return the first status character, the only well-supported field."""
        return self.status.arming_state

    @property
    def status_2(self) -> str:
        """Return the second status character."""
        return self.status.status_2

    @property
    def status_3(self) -> str:
        """Return the third status character."""
        return self.status.status_3

    @property
    def status_4(self) -> str:
        """Return the fourth status character."""
        return self.status.status_4


@dataclass(slots=True)
class AreaStatusPage:
    """One parsed `?WA` reply page."""

    areas: list[AreaStatusRecord]
    complete: bool
    raw_reply: bytes


@dataclass(slots=True)
class AreaStatusReply:
    """Parsed result of a complete `?WA` transaction."""

    areas: list[AreaStatusRecord]
    complete: bool
    raw_replies: list[bytes]


@dataclass(slots=True)
class AreaStatusCollection:
    """Internal result for a complete `?WA` collection loop."""

    areas: list[AreaStatusRecord]
    raw_replies: list[bytes]
    complete: bool


class TransactionQueryAreas(Transaction):
    """Complete `?WA` area-status transaction.

    This transaction owns the full paging loop. Callers submit one transaction,
    and it continues with bare `?WA` requests until the panel signals the
    terminal `--` marker.
    """

    __slots__ = ("area",)

    def __init__(self, area: int | str = 1) -> None:
        normalized_area = normalize_area_number(area)
        super().__init__(
            body=f"?WA{normalized_area}",
            completion=payload_required(),
            label="query_areas",
        )
        self.area = normalized_area

    async def execute_in_session(
        self,
        exchange: TransactionRunner,
        *,
        session_mode,
        endpoint=None,
    ) -> Transaction:
        del endpoint
        collected = await collect_area_status(
            self,
            exchange,
            start_area=self.area,
            session_mode=session_mode,
        )
        self.parsed_response = AreaStatusReply(
            areas=collected.areas,
            complete=collected.complete,
            raw_replies=collected.raw_replies,
        )
        return self


def normalize_area_number(area: int | str) -> str:
    """Normalize an area number to the documented 2-digit `?WA` format.

    Current official XR-series references support area numbers 1 through 32.
    """
    if isinstance(area, int):
        value = area
    else:
        text = str(area).strip()
        if not text.isdigit():
            raise ValueError(f"Area must be numeric, got: {area!r}")
        value = int(text)

    if not 1 <= value <= 32:
        raise ValueError(f"Area must be between 1 and 32, got: {value}")

    return f"{value:02d}"


async def collect_area_status(
    transaction: Transaction,
    exchange: TransactionRunner,
    *,
    start_area: str,
    session_mode,
) -> AreaStatusCollection:
    """Collect a full paged `?WA` result inside an active session."""
    current_body: bytes | str = f"?WA{start_area}"
    collected_areas: list[AreaStatusRecord] = []
    raw_replies: list[bytes] = []
    completion: CompletionPolicy = transaction.completion

    while True:
        exchange_result = await exchange(current_body, completion)
        transaction.record_exchange(exchange_result, session_mode=session_mode)

        if exchange_result.response is None:
            raise SessionProtocolError("Area query completed without a reply payload")

        page = parse_area_status_page(exchange_result.response)
        raw_replies.append(page.raw_reply)
        collected_areas.extend(page.areas)

        if page.complete:
            return AreaStatusCollection(
                areas=collected_areas,
                raw_replies=raw_replies,
                complete=True,
            )

        current_body = AREA_QUERY_CONTINUATION_BODY


def parse_area_status_page(reply: bytes) -> AreaStatusPage:
    """Parse one raw panel reply page for the `?WA` family."""
    payload = _extract_area_payload(reply)
    cleaned = payload.rstrip(b"\r\x00")
    if cleaned == b"--":
        return AreaStatusPage(areas=[], complete=True, raw_reply=reply)

    parts = [part for part in cleaned.split(AREA_RECORD_SEPARATOR) if part]
    areas: list[AreaStatusRecord] = []
    complete = False

    for part in parts:
        if part == b"--":
            complete = True
            continue

        if len(part) < 6:
            raise SessionProtocolError(f"Malformed ?WA area record: {part!r}")

        number = part[0:2].decode("ascii", errors="strict")
        raw_status = part[2:6].decode("ascii", errors="strict")
        status = parse_area_status_block(raw_status)
        name = part[6:].decode("ascii", errors="replace").strip()
        areas.append(AreaStatusRecord(number=number, status=status, name=name))

    return AreaStatusPage(areas=areas, complete=complete, raw_reply=reply)


def parse_area_status_block(raw_status: str) -> AreaStatusBlock:
    """Split the 4-character area status block into the smallest clear pieces."""
    if len(raw_status) != 4:
        raise SessionProtocolError(
            f"Expected a 4-character ?WA status block, got: {raw_status!r}"
        )

    return AreaStatusBlock(
        arming_state=raw_status[0],
        status_2=raw_status[1],
        status_3=raw_status[2],
        status_4=raw_status[3],
    )


def _extract_area_payload(reply: bytes) -> bytes:
    """Extract the body that follows the `*WA`/`!WA`/`?WA` marker."""
    for marker in AREA_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index + len(marker) :]

    raise SessionProtocolError("Reply did not contain a WA marker")
