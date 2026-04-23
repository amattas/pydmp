"""Stateless `?WQ` output-status transaction and reply parsing.

`?WQ` can walk several selector families. By default we stay in the numeric
family and only return named rows, but the parser keeps enough structure for
callers to inspect the raw mixed rows too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .errors import SessionProtocolError
from .models import (
    PanelEndpoint,
    Transaction,
    TransactionRunner,
    payload_required,
)

OUTPUT_RECORD_SEPARATOR: Final[bytes] = b"\x1e"
OUTPUT_REPLY_PREFIXES: Final[tuple[bytes, ...]] = (b"*WQ", b"!WQ", b"?WQ")
OUTPUT_PAGE_TERMINATOR: Final[bytes] = b"---"
OUTPUT_START_SELECTOR: Final[str] = "001"
OUTPUT_MAX_PAGES: Final[int] = 200
OUTPUT_NUMERIC_MAX_SELECTOR: Final[int] = 999
OUTPUT_NAMESPACE_MAX_SELECTOR: Final[int] = 99
OUTPUT_MAX_ROWS_PER_PAGE: Final[int] = 11
OUTPUT_NAMESPACE_PREFIXES: Final[frozenset[str]] = frozenset({"D", "F", "G"})


@dataclass(slots=True)
class OutputStatusRecord:
    """One parsed row from a `?WQ` reply."""

    selector: str
    status: str
    name: str

    @property
    def namespace(self) -> str:
        """Return `numeric`, `D`, `F`, or `G` for the selector family."""
        if self.selector[:1].isdigit():
            return "numeric"
        return self.selector[:1]

    @property
    def number(self) -> int | None:
        """Return the numeric selector value, or None for non-numeric namespaces."""
        if not self.selector[:1].isdigit():
            return None
        return int(self.selector, 10)

    @property
    def stripped_name(self) -> str:
        """Return the display name with leading/trailing padding removed."""
        return self.name.strip()

    @property
    def is_unused(self) -> bool:
        """Return True for the visible `* UNUSED *` placeholder rows."""
        return self.stripped_name.upper() == "* UNUSED *"

    @property
    def has_name(self) -> bool:
        """Return True when the row has a non-empty visible name."""
        return bool(self.stripped_name)

    @property
    def is_named_output(self) -> bool:
        """Return True for rows with a real visible name, excluding placeholders."""
        return self.has_name and not self.is_unused


@dataclass(slots=True)
class OutputStatusPage:
    """One parsed `?WQ` reply page."""

    records: list[OutputStatusRecord]
    empty_terminal_page: bool
    raw_reply: bytes


@dataclass(slots=True)
class OutputStatusReply:
    """Parsed result of a complete `?WQ` output-status transaction.

    `records` contains the selected namespace after applying the caller's
    name filter. `all_records` preserves the raw rows seen on the wire.
    """

    records: list[OutputStatusRecord]
    complete: bool
    raw_replies: list[bytes]
    all_records: list[OutputStatusRecord] | None = None
    namespace: str = "numeric"
    named_only: bool = True

    def __post_init__(self) -> None:
        if self.all_records is None:
            self.all_records = list(self.records)

    @property
    def outputs(self) -> list[OutputStatusRecord]:
        """Return only numeric rows from the filtered record set."""
        return [record for record in self.records if record.namespace == "numeric"]

    @property
    def all_outputs(self) -> list[OutputStatusRecord]:
        """Return only numeric rows from the unfiltered raw record set."""
        return [record for record in self.all_records or [] if record.namespace == "numeric"]


class TransactionQueryOutputs(Transaction):
    """Complete paged `?WQ` query using one explicit visible selector family."""

    __slots__ = ("max_pages", "named_only", "namespace", "start_selector")

    def __init__(
        self,
        start_selector: int | str = OUTPUT_START_SELECTOR,
        *,
        namespace: str | None = None,
        named_only: bool = True,
        max_pages: int = OUTPUT_MAX_PAGES,
    ) -> None:
        normalized_selector, normalized_namespace = normalize_output_query_start(
            start_selector,
            namespace=namespace,
        )
        if max_pages < 1:
            raise ValueError(f"max_pages must be >= 1, got: {max_pages!r}")
        super().__init__(body=f"?WQ{normalized_selector}", completion=payload_required(), label="query_outputs")
        self.start_selector = normalized_selector
        self.namespace = normalized_namespace
        self.named_only = bool(named_only)
        self.max_pages = int(max_pages)

    async def execute_in_session(
        self,
        exchange: TransactionRunner,
        *,
        session_mode,
        endpoint: PanelEndpoint | None = None,
    ) -> Transaction:
        del endpoint

        selector = self.start_selector
        records: list[OutputStatusRecord] = []
        raw_replies: list[bytes] = []
        seen_start_selectors: set[str] = set()

        for _page_index in range(self.max_pages):
            if selector in seen_start_selectors:
                raise SessionProtocolError(
                    f"Output query selector walk repeated at {selector!r}"
                )
            seen_start_selectors.add(selector)

            exchange_result = await exchange(f"?WQ{selector}", self.completion)
            self.record_exchange(exchange_result, session_mode=session_mode)

            if exchange_result.response is None:
                raise SessionProtocolError("Output query completed without a reply payload")

            page = parse_output_status_page(exchange_result.response)
            raw_replies.append(page.raw_reply)

            if page.empty_terminal_page:
                self.parsed_response = OutputStatusReply(records=_filter_output_records(records, namespace=self.namespace, named_only=self.named_only), complete=True, raw_replies=raw_replies, all_records=records, namespace=self.namespace, named_only=self.named_only)
                return self

            records.extend(page.records)
            # Reseed using the highest visible selector from the same family.
            # This matches the way the panel exposes numeric and namespaced
            # output walks in project captures.
            next_selector = _next_output_selector(
                current_selector=selector,
                records=page.records,
            )
            if next_selector is None:
                self.parsed_response = OutputStatusReply(records=_filter_output_records(records, namespace=self.namespace, named_only=self.named_only), complete=True, raw_replies=raw_replies, all_records=records, namespace=self.namespace, named_only=self.named_only)
                return self
            if _compare_output_selectors(next_selector, selector) <= 0:
                raise SessionProtocolError(
                    f"Output query selector walk did not advance: {selector!r} -> {next_selector!r}"
                )
            selector = next_selector

        raise SessionProtocolError("Output query exceeded max page count")


def normalize_output_selector(selector: int | str) -> str:
    """Normalize a `?WQ` selector to `001` or namespace form like `D01`."""
    if isinstance(selector, int):
        if not 1 <= selector <= OUTPUT_NUMERIC_MAX_SELECTOR:
            raise ValueError(f"Output selector must be 1..999, got: {selector}")
        return f"{selector:03d}"

    text = str(selector).strip().upper()
    if text.startswith("?WQ"):
        text = text[3:]
    if not text:
        raise ValueError("Output selector must not be empty")

    prefix = text[:1]
    if prefix in OUTPUT_NAMESPACE_PREFIXES:
        suffix = text[1:]
        if not suffix.isdigit():
            raise ValueError(f"Malformed WQ namespace selector: {selector!r}")
        value = int(suffix, 10)
        if not 1 <= value <= OUTPUT_NAMESPACE_MAX_SELECTOR:
            raise ValueError(f"WQ namespace selector must be 01..99, got: {selector!r}")
        return f"{prefix}{value:02d}"

    if not text.isdigit():
        raise ValueError(f"Malformed WQ selector: {selector!r}")

    value = int(text, 10)
    if not 1 <= value <= OUTPUT_NUMERIC_MAX_SELECTOR:
        raise ValueError(f"Output selector must be 1..999, got: {selector!r}")
    return f"{value:03d}"


def parse_output_status_page(reply: bytes) -> OutputStatusPage:
    """Parse one raw panel reply page for the `?WQ` family.

    A non-empty page is a series of output rows separated by `0x1e`, followed
    by `0x1e---`. The fully empty terminal page is just `---`.
    """
    payload = _extract_output_payload(reply)
    cleaned = payload.rstrip(b"\r\x00")
    if cleaned == OUTPUT_PAGE_TERMINATOR:
        return OutputStatusPage(records=[], empty_terminal_page=True, raw_reply=reply)
    if not cleaned:
        raise SessionProtocolError("Empty ?WQ reply payload")
    if not cleaned.endswith(OUTPUT_RECORD_SEPARATOR + OUTPUT_PAGE_TERMINATOR):
        raise SessionProtocolError(f"Malformed ?WQ reply missing terminator: {reply!r}")

    parts = cleaned.split(OUTPUT_RECORD_SEPARATOR)
    records: list[OutputStatusRecord] = []
    saw_terminator = False

    for part in parts:
        if not part:
            raise SessionProtocolError(f"Malformed ?WQ reply contained an empty record: {reply!r}")
        if saw_terminator:
            raise SessionProtocolError(f"Malformed ?WQ reply contained data after terminator: {reply!r}")
        if part == OUTPUT_PAGE_TERMINATOR:
            saw_terminator = True
            continue
        records.append(_parse_output_row(part))
        if len(records) > OUTPUT_MAX_ROWS_PER_PAGE:
            raise SessionProtocolError(
                f"Malformed ?WQ reply exceeded {OUTPUT_MAX_ROWS_PER_PAGE} rows: {reply!r}"
            )

    if not saw_terminator:
        raise SessionProtocolError(f"Malformed ?WQ reply missing terminator: {reply!r}")

    return OutputStatusPage(records=records, empty_terminal_page=False, raw_reply=reply)


def _parse_output_row(raw_row: bytes) -> OutputStatusRecord:
    """Parse one `<selector><status><optional name>` `?WQ` row."""
    if len(raw_row) < 4:
        raise SessionProtocolError(f"Malformed ?WQ output row: {raw_row!r}")

    first = raw_row[:1].decode("ascii", errors="strict")
    if first in OUTPUT_NAMESPACE_PREFIXES:
        selector_bytes = raw_row[:3]
        if len(selector_bytes) != 3 or not selector_bytes[1:3].isdigit():
            raise SessionProtocolError(f"Malformed ?WQ namespaced selector: {raw_row!r}")
    elif raw_row[:3].isdigit():
        selector_bytes = raw_row[:3]
    else:
        raise SessionProtocolError(f"Malformed ?WQ selector: {raw_row!r}")

    if len(raw_row) <= len(selector_bytes):
        raise SessionProtocolError(f"Missing ?WQ status character: {raw_row!r}")

    selector = selector_bytes.decode("ascii", errors="strict")
    status = raw_row[3:4].decode("ascii", errors="strict")
    name = raw_row[4:].decode("ascii", errors="replace").rstrip()

    return OutputStatusRecord(selector=selector, status=status, name=name)


def _next_output_selector(*, current_selector: str, records: list[OutputStatusRecord]) -> str | None:
    """Return the next seeded selector inside the current visible family."""
    if not records:
        return None

    family = _selector_family(current_selector)
    family_records = [record for record in records if _selector_family(record.selector) == family]
    if not family_records:
        return None

    if family == "numeric":
        visible_values = [int(record.selector, 10) for record in family_records]
        value = max(visible_values) + 1
        if value <= OUTPUT_NUMERIC_MAX_SELECTOR:
            return f"{value:03d}"
        return None

    prefix = family
    visible_values = [int(record.selector[1:], 10) for record in family_records]
    value = max(visible_values) + 1
    if value <= OUTPUT_NAMESPACE_MAX_SELECTOR:
        return f"{prefix}{value:02d}"
    return None


def normalize_output_query_namespace(namespace: str | None) -> str | None:
    """Normalize a query namespace to `numeric`, `D`, `F`, or `G`."""
    if namespace is None:
        return None

    text = str(namespace).strip().upper()
    if text in {"", "AUTO"}:
        return None
    if text in {"NUMERIC", "OUTPUT", "OUTPUTS", "N"}:
        return "numeric"
    if text in OUTPUT_NAMESPACE_PREFIXES:
        return text
    raise ValueError(f"Output query namespace must be numeric, D, F, or G: {namespace!r}")


def normalize_output_query_start(
    start_selector: int | str,
    *,
    namespace: str | None = None,
) -> tuple[str, str]:
    """Return the seeded visible selector plus its selected query namespace.

    This helper keeps two ideas aligned:

    - what selector we will actually send on the wire
    - what family the caller expects back from the filtered result
    """
    normalized_selector = normalize_output_selector(start_selector)
    inferred_namespace = _selector_family(normalized_selector)
    requested_namespace = normalize_output_query_namespace(namespace)

    if requested_namespace is None:
        return normalized_selector, inferred_namespace

    if requested_namespace == "numeric":
        if inferred_namespace != "numeric":
            raise ValueError(
                f"Output query namespace {requested_namespace!r} does not match start selector {start_selector!r}"
            )
        return normalized_selector, requested_namespace

    if inferred_namespace == requested_namespace:
        return normalized_selector, requested_namespace
    if inferred_namespace != "numeric":
        raise ValueError(
            f"Output query namespace {requested_namespace!r} does not match start selector {start_selector!r}"
        )

    numeric_value = int(normalized_selector, 10)
    if not 1 <= numeric_value <= OUTPUT_NAMESPACE_MAX_SELECTOR:
        raise ValueError(
            f"Namespaced WQ query start must be 01..99, got: {start_selector!r}"
        )
    return f"{requested_namespace}{numeric_value:02d}", requested_namespace


def _extract_output_payload(reply: bytes) -> bytes:
    """Extract the body that follows the `*WQ`/`!WQ`/`?WQ` marker."""
    for marker in OUTPUT_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index + len(marker) :]

    raise SessionProtocolError("Reply did not contain a WQ marker")


def _selector_family(selector: str) -> str:
    """Return `numeric` or the visible namespace letter for one selector."""
    if selector[:1].isdigit():
        return "numeric"
    return selector[:1]


def _compare_output_selectors(left: str, right: str) -> int:
    """Compare two visible selectors within one family for no-progress checks."""
    left_family = _selector_family(left)
    right_family = _selector_family(right)
    if left_family != right_family:
        return (left_family > right_family) - (left_family < right_family)
    if left_family == "numeric":
        return int(left, 10) - int(right, 10)
    return int(left[1:], 10) - int(right[1:], 10)


def _filter_output_records(
    records: list[OutputStatusRecord],
    *,
    namespace: str,
    named_only: bool,
) -> list[OutputStatusRecord]:
    """Filter the raw mixed `WQ` rows to the selected family and name policy."""
    filtered = [record for record in records if record.namespace == namespace]
    if not named_only:
        return filtered
    return [record for record in filtered if record.is_named_output]
