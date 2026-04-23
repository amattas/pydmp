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
AREA_QUERY_INITIAL_BODY = "?WA01"
AREA_QUERY_CONTINUATION_BODY = "?WA"
AREA_QUERY_MAX_PAGES = 64
AREA_NAME_MAX_LENGTH = 32
AREA_STATUS_1_CHARS = frozenset("NYB")
AREA_STATUS_2_TO_4_CHARS = frozenset("NY")


@dataclass(slots=True)
class AreaStatusBlock:
    """One parsed 4-character `?WA` status block.

    Firmware RE ties the four characters to the low bits of the per-area status
    word at `0xa00425ec + (area_index + 0x20) * 4`:
    - state / bit 0x01: rendered as `N`, `Y`, or special `B`
    - unknown / bit 0x02: no observed product meaning; treat as reserved/unused
    - schedule_active / bit 0x04
    - late_to_close / bit 0x08
    """

    state: str
    unknown: str
    schedule_active: str
    late_to_close: str
    raw: str = ""

    @property
    def text(self) -> str:
        """Return the full observed status text."""
        return (
            self.raw
            or self.state + self.unknown + self.schedule_active + self.late_to_close
        )


@dataclass(slots=True)
class AreaStatusRecord:
    """One parsed area record from a `?WA` reply."""

    number: str
    status: AreaStatusBlock
    name: str

    @property
    def state(self) -> str:
        """Return the first status character."""
        return self.status.state

    @property
    def unknown(self) -> str:
        """Return the second status character."""
        return self.status.unknown

    @property
    def schedule_active(self) -> str:
        """Return the third status character."""
        return self.status.schedule_active

    @property
    def late_to_close(self) -> str:
        """Return the fourth status character."""
        return self.status.late_to_close

    @property
    def status_text(self) -> str:
        """Return the full observed status text."""
        return self.status.text


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
    """Complete full-panel `?WA` area-status transaction.

    This transaction owns the full paging loop. Callers submit one transaction,
    and it starts at area `01`, then continues with bare `?WA` requests until
    the panel signals the terminal `--` marker.
    """

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(
            body=AREA_QUERY_INITIAL_BODY,
            completion=payload_required(),
            label="query_areas",
        )

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
            session_mode=session_mode,
        )
        self.parsed_response = AreaStatusReply(
            areas=collected.areas,
            complete=collected.complete,
            raw_replies=collected.raw_replies,
        )
        return self


async def collect_area_status(
    transaction: Transaction,
    exchange: TransactionRunner,
    *,
    session_mode,
) -> AreaStatusCollection:
    """Collect a full paged `?WA` result inside an active session."""
    current_body: bytes | str = AREA_QUERY_INITIAL_BODY
    collected_areas: list[AreaStatusRecord] = []
    raw_replies: list[bytes] = []
    completion: CompletionPolicy = transaction.completion
    seen_pages: set[bytes] = set()

    for _page_number in range(AREA_QUERY_MAX_PAGES):
        exchange_result = await exchange(current_body, completion)
        transaction.record_exchange(exchange_result, session_mode=session_mode)

        if exchange_result.response is None:
            raise SessionProtocolError("Area query completed without a reply payload")

        page = parse_area_status_page(exchange_result.response)
        page_signature = _area_payload_signature(exchange_result.response)
        if page_signature in seen_pages and not page.complete:
            return AreaStatusCollection(
                areas=collected_areas,
                raw_replies=raw_replies,
                complete=False,
            )
        seen_pages.add(page_signature)

        raw_replies.append(page.raw_reply)
        collected_areas.extend(page.areas)

        if page.complete:
            return AreaStatusCollection(
                areas=collected_areas,
                raw_replies=raw_replies,
                complete=True,
            )

        current_body = AREA_QUERY_CONTINUATION_BODY

    raise SessionProtocolError(
        f"Area query exceeded {AREA_QUERY_MAX_PAGES} pages without a terminator"
    )


def parse_area_status_page(reply: bytes) -> AreaStatusPage:
    """Parse one raw panel reply page for the `?WA` family."""
    payload = _extract_area_payload(reply)
    cleaned = payload.rstrip(b"\r\x00")
    if cleaned == b"--":
        return AreaStatusPage(areas=[], complete=True, raw_reply=reply)
    if not cleaned:
        raise SessionProtocolError("Empty ?WA reply payload")

    parts = cleaned.split(AREA_RECORD_SEPARATOR)
    areas: list[AreaStatusRecord] = []
    complete = False

    for part in parts:
        if not part:
            raise SessionProtocolError(f"Malformed ?WA reply contained an empty record: {reply!r}")
        if complete:
            raise SessionProtocolError(f"Malformed ?WA reply contained data after terminator: {reply!r}")
        if part == b"--":
            complete = True
            continue

        areas.append(_parse_area_record(part))

    return AreaStatusPage(areas=areas, complete=complete, raw_reply=reply)


def parse_area_status_block(raw_status: str) -> AreaStatusBlock:
    """Split the 4-character area status block into the smallest clear pieces."""
    if len(raw_status) != 4:
        raise SessionProtocolError(
            f"Expected a 4-character ?WA status block, got: {raw_status!r}"
        )
    if raw_status[0] not in AREA_STATUS_1_CHARS:
        raise SessionProtocolError(f"Unexpected ?WA state character: {raw_status!r}")
    if any(char not in AREA_STATUS_2_TO_4_CHARS for char in raw_status[1:]):
        raise SessionProtocolError(f"Unexpected ?WA status block characters: {raw_status!r}")

    return AreaStatusBlock(
        state=raw_status[0],
        unknown=raw_status[1],
        schedule_active=raw_status[2],
        late_to_close=raw_status[3],
        raw=raw_status,
    )


def _parse_area_record(raw_record: bytes) -> AreaStatusRecord:
    """Parse one `?WA` area row.

    Current support is intentionally limited to the XR/213-backed shape:
    `%02d + status4 + name`.
    """
    if len(raw_record) < 7:
        raise SessionProtocolError(f"Malformed ?WA area record: {raw_record!r}")

    try:
        number = raw_record[0:2].decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise SessionProtocolError(f"Malformed ?WA area number: {raw_record!r}") from exc
    if not number.isdigit():
        raise SessionProtocolError(f"Malformed ?WA area number: {raw_record!r}")
    area_number = int(number)
    if not 1 <= area_number <= 32:
        raise SessionProtocolError(f"?WA area number out of range: {number!r}")

    body = raw_record[2:]
    if not _looks_like_area_status(body[:4]):
        raise SessionProtocolError(f"Malformed ?WA area status block: {raw_record!r}")

    raw_status = body[:4].decode("ascii", errors="strict")
    name = _decode_area_name(body[4:], raw_record)
    return AreaStatusRecord(
        number=number,
        status=parse_area_status_block(raw_status),
        name=name,
    )


def _looks_like_area_status(value: bytes) -> bool:
    if len(value) < 4:
        return False
    try:
        decoded = value[:4].decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return False
    return (
        decoded[0] in AREA_STATUS_1_CHARS
        and all(char in AREA_STATUS_2_TO_4_CHARS for char in decoded[1:])
    )


def _decode_area_name(raw_name: bytes, raw_record: bytes) -> str:
    try:
        decoded = raw_name.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise SessionProtocolError(f"Malformed ?WA area name: {raw_record!r}") from exc

    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in decoded):
        raise SessionProtocolError(f"Malformed ?WA area name: {raw_record!r}")

    name = decoded.strip()
    if not name:
        raise SessionProtocolError(f"Malformed ?WA area record missing area name: {raw_record!r}")
    if len(name) > AREA_NAME_MAX_LENGTH:
        raise SessionProtocolError(f"Malformed ?WA area name exceeds {AREA_NAME_MAX_LENGTH} chars: {raw_record!r}")
    return name


def _area_payload_signature(reply: bytes) -> bytes:
    return _extract_area_payload(reply).rstrip(b"\r\x00")


def _extract_area_payload(reply: bytes) -> bytes:
    """Extract the body that follows the `*WA`/`!WA`/`?WA` marker."""
    for marker in AREA_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index + len(marker) :]

    raise SessionProtocolError("Reply did not contain a WA marker")
