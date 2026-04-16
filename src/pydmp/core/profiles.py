"""Stateless `?U` profile-table transaction and reply parsing."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SessionProtocolError
from .models import (
    PanelEndpoint,
    Transaction,
    TransactionRunner,
    payload_required,
)

PROFILE_RECORD_SEPARATOR = b"\x1e"
PROFILE_REPLY_PREFIXES = (b"*U", b"!U", b"?U")
PROFILE_START_SELECTOR = "000"
PROFILE_MAX_SELECTOR = 999
PROFILE_MAX_PAGES = 200


@dataclass(slots=True)
class ProfileRecord:
    """One parsed profile record from a `?U` reply."""

    number: str
    areas_mask: str
    access_areas_mask: str
    output_group: str
    menu_options: str
    field_30_45: str | None
    rearm_delay: str | None
    field_49_63: str | None
    name: str


@dataclass(slots=True)
class ProfilePage:
    """One parsed `?U` reply page."""

    profiles: list[ProfileRecord]
    has_terminal_marker: bool
    raw_reply: bytes


@dataclass(slots=True)
class ProfileReply:
    """Parsed result of a complete `?U` profile-table transaction."""

    profiles: list[ProfileRecord]
    complete: bool
    raw_replies: list[bytes]


class TransactionQueryProfiles(Transaction):
    """Complete paged profile-table query using normal selector advancement."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(
            body=f"?U{PROFILE_START_SELECTOR}",
            completion=payload_required(),
            label="query_profiles",
        )

    async def execute_in_session(
        self,
        exchange: TransactionRunner,
        *,
        session_mode,
        endpoint: PanelEndpoint | None = None,
    ) -> Transaction:
        del endpoint

        selector = PROFILE_START_SELECTOR
        profiles: list[ProfileRecord] = []
        raw_replies: list[bytes] = []
        pages = 0

        while pages < PROFILE_MAX_PAGES:
            pages += 1
            exchange_result = await exchange(f"?U{selector}", self.completion)
            self.record_exchange(exchange_result, session_mode=session_mode)

            if exchange_result.response is None:
                raise SessionProtocolError("Profile query completed without a reply payload")

            page = parse_profile_page(exchange_result.response)
            raw_replies.append(page.raw_reply)
            profiles.extend(page.profiles)

            next_selector = _next_profile_selector(
                current_selector=int(selector, 10),
                profiles=page.profiles,
            )
            if next_selector is None:
                self.parsed_response = ProfileReply(
                    profiles=profiles,
                    complete=True,
                    raw_replies=raw_replies,
                )
                return self

            selector = next_selector

        raise SessionProtocolError("Profile query exceeded max page count")


def parse_profile_page(reply: bytes) -> ProfilePage:
    """Parse one raw panel reply page for the `?U` family."""
    payload = _extract_profile_payload(reply)
    cleaned = payload.rstrip(b"\r\x00")
    if cleaned == b"----":
        return ProfilePage(profiles=[], has_terminal_marker=True, raw_reply=reply)

    parts = [part for part in cleaned.split(PROFILE_RECORD_SEPARATOR) if part]
    profiles: list[ProfileRecord] = []
    has_terminal_marker = False

    for part in parts:
        if part == b"----":
            has_terminal_marker = True
            continue

        raw_record = part.decode("ascii", errors="strict")
        profiles.append(_parse_profile_record(raw_record))

    return ProfilePage(
        profiles=profiles,
        has_terminal_marker=has_terminal_marker,
        raw_reply=reply,
    )


def _parse_profile_record(raw_record: str) -> ProfileRecord:
    """Parse one cleartext profile record from a `?U` page."""
    if len(raw_record) < 30:
        raise SessionProtocolError(f"Malformed ?U profile record: {raw_record!r}")

    field_30_45 = raw_record[30:46] if len(raw_record) >= 46 else None
    rearm_delay = raw_record[46:49] if len(raw_record) >= 49 else None
    field_49_63 = raw_record[49:64] if len(raw_record) >= 64 else None

    if len(raw_record) >= 64:
        name = raw_record[64:]
    elif len(raw_record) >= 49:
        name = raw_record[49:]
    else:
        name = raw_record[30:]

    return ProfileRecord(
        number=raw_record[0:3],
        areas_mask=raw_record[3:11],
        access_areas_mask=raw_record[11:19],
        output_group=raw_record[19:22],
        menu_options=raw_record[22:30],
        field_30_45=field_30_45,
        rearm_delay=rearm_delay,
        field_49_63=field_49_63,
        name=name,
    )


def _next_profile_selector(*, current_selector: int, profiles: list[ProfileRecord]) -> str | None:
    """Return the next selector using the observed profile-page behavior."""
    if not profiles:
        return None

    profile_numbers = [int(profile.number, 10) for profile in profiles if profile.number.isdigit()]
    if not profile_numbers:
        return None

    positive_numbers = [value for value in profile_numbers if value > 0]
    if positive_numbers:
        candidate = max(positive_numbers) + 1
    elif max(profile_numbers) == 0:
        candidate = max(current_selector, 1)
    else:
        return None

    if candidate <= current_selector or candidate > PROFILE_MAX_SELECTOR:
        return None

    return f"{candidate:03d}"


def _extract_profile_payload(reply: bytes) -> bytes:
    """Extract the body that follows the `*U`/`!U`/`?U` marker."""
    for marker in PROFILE_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index + len(marker) :]

    raise SessionProtocolError("Reply did not contain a U marker")
