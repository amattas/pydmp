"""Stateless `?U` profile-table transaction and reply parsing.

`?U` exposes the visible profile table. This module keeps the wire handling
strict while also breaking the known profile fields into smaller, friendlier
properties for callers.
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

PROFILE_RECORD_SEPARATOR: Final[bytes] = b"\x1e"
PROFILE_REPLY_PREFIXES: Final[tuple[bytes, ...]] = (b"*U", b"!U", b"?U")
PROFILE_START_SELECTOR: Final[str] = "000"
PROFILE_MAX_SELECTOR: Final[int] = 999
PROFILE_MAX_PAGES: Final[int] = 200
PROFILE_MAX_ROWS_PER_PAGE: Final[int] = 4
PROFILE_PAGE_TERMINATOR: Final[bytes] = b"----"
PROFILE_LEGACY_MIN_FIXED_WIDTH: Final[int] = 49
PROFILE_CURRENT_FIXED_WIDTH: Final[int] = 64


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

    @property
    def arm_disarm_areas_mask(self) -> str:
        """Raw 32-area arm/disarm bitmap as rendered by `?U`."""
        return self.areas_mask

    @property
    def arm_disarm_areas(self) -> tuple[int, ...]:
        """Decoded arm/disarm area numbers from the bitmap field."""
        return _decode_profile_area_mask(self.areas_mask)

    @property
    def access_areas(self) -> tuple[int, ...]:
        """Decoded access area numbers from the bitmap field."""
        return _decode_profile_area_mask(self.access_areas_mask)

    @property
    def output_group_number(self) -> int | None:
        """Output-group number, or `None` when the wire value is `000`."""
        if self.output_group == "000":
            return None
        if self.output_group.isdigit():
            return int(self.output_group, 10)
        return None

    @property
    def menu_options_raw(self) -> str:
        """Raw 4-byte permission/options word."""
        return self.menu_options

    @property
    def menu_option_byte_1(self) -> int:
        return _decode_profile_option_byte(self.menu_options, 0)

    @property
    def menu_option_byte_2(self) -> int:
        return _decode_profile_option_byte(self.menu_options, 1)

    @property
    def menu_option_byte_3(self) -> int:
        return _decode_profile_option_byte(self.menu_options, 2)

    @property
    def menu_option_byte_4(self) -> int:
        return _decode_profile_option_byte(self.menu_options, 3)

    @property
    def disarm_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 0, 0x01)

    @property
    def alarm_silence_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 0, 0x02)

    @property
    def sensor_reset_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 0, 0x04)

    @property
    def lockdown_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 0, 0x08)

    @property
    def door_unlock_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 0, 0x10)

    @property
    def door_access_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 0, 0x20)

    @property
    def arm_area_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 0, 0x40)

    @property
    def outputs_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 0, 0x80)

    @property
    def zone_status_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 1, 0x01)

    @property
    def bypass_zone_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 1, 0x02)

    @property
    def zone_monitor_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 1, 0x04)

    @property
    def system_status_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 1, 0x08)

    @property
    def system_test_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 1, 0x10)

    @property
    def profiles_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 1, 0x20)

    @property
    def user_code_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 1, 0x40)

    @property
    def extend_schedules(self) -> bool:
        return _profile_option_bit(self.menu_options, 1, 0x80)

    @property
    def schedules_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 2, 0x01)

    @property
    def time_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 2, 0x02)

    @property
    def display_events(self) -> bool:
        return _profile_option_bit(self.menu_options, 2, 0x04)

    @property
    def service_request_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 2, 0x08)

    @property
    def fire_drill_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 2, 0x10)

    @property
    def anti_passback_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 2, 0x40)

    @property
    def arm_permission(self) -> bool:
        return _profile_option_bit(self.menu_options, 2, 0x80)

    @property
    def easy_arm_disarm(self) -> bool:
        return _profile_option_bit(self.menu_options, 3, 0x01)

    @property
    def card_plus_pin(self) -> bool:
        return _profile_option_bit(self.menu_options, 3, 0x04)

    @property
    def wifi_setup(self) -> bool:
        return _profile_option_bit(self.menu_options, 3, 0x08)

    @property
    def technician_user(self) -> bool:
        return _profile_option_bit(self.menu_options, 3, 0x10)

    @property
    def access_schedule_cells_raw(self) -> str | None:
        """Raw 8-cell access-schedule block."""
        return self.field_30_45

    @property
    def access_schedule_cells(self) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None, str | None, str | None]:
        raw = self.field_30_45 or ""
        cells = tuple(_decode_profile_schedule_cell(raw[index:index + 2]) for index in range(0, 16, 2))
        return cells  # type: ignore[return-value]

    @property
    def first_access_schedule(self) -> str | None:
        return self.access_schedule_cells[0]

    @property
    def second_access_schedule(self) -> str | None:
        return self.access_schedule_cells[1]

    @property
    def third_access_schedule(self) -> str | None:
        return self.access_schedule_cells[2]

    @property
    def fourth_access_schedule(self) -> str | None:
        return self.access_schedule_cells[3]

    @property
    def fifth_access_schedule(self) -> str | None:
        return self.access_schedule_cells[4]

    @property
    def sixth_access_schedule(self) -> str | None:
        return self.access_schedule_cells[5]

    @property
    def seventh_access_schedule(self) -> str | None:
        return self.access_schedule_cells[6]

    @property
    def eighth_access_schedule(self) -> str | None:
        return self.access_schedule_cells[7]

    @property
    def tail_01(self) -> str | None:
        return self.rearm_delay

    @property
    def tail_02(self) -> str | None:
        return _decode_profile_tail_cell(self.field_49_63, 0)

    @property
    def tail_03(self) -> str | None:
        return _decode_profile_tail_cell(self.field_49_63, 1)

    @property
    def tail_04(self) -> str | None:
        return _decode_profile_tail_cell(self.field_49_63, 2)

    @property
    def tail_05(self) -> str | None:
        return _decode_profile_tail_cell(self.field_49_63, 3)

    @property
    def tail_06(self) -> str | None:
        return _decode_profile_tail_cell(self.field_49_63, 4)


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
        super().__init__(body=f"?U{PROFILE_START_SELECTOR}", completion=payload_required(), label="query_profiles")

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
        seen_start_selectors: set[str] = set()

        while pages < PROFILE_MAX_PAGES:
            pages += 1
            if selector in seen_start_selectors:
                raise SessionProtocolError(f"Profile query selector walk repeated at {selector!r}")
            seen_start_selectors.add(selector)

            exchange_result = await exchange(f"?U{selector}", self.completion)
            self.record_exchange(exchange_result, session_mode=session_mode)

            if exchange_result.response is None:
                raise SessionProtocolError("Profile query completed without a reply payload")

            page = parse_profile_page(exchange_result.response)
            raw_replies.append(page.raw_reply)
            profiles.extend(page.profiles)

            # `?U` also uses seeded continuation. We ask again starting at the
            # highest visible profile plus one.
            next_selector = _next_profile_selector(profiles=page.profiles)
            if next_selector is None:
                self.parsed_response = ProfileReply(profiles=profiles, complete=True, raw_replies=raw_replies)
                return self

            if int(next_selector, 10) <= int(selector, 10):
                raise SessionProtocolError(
                    f"Profile query selector walk did not advance: {selector!r} -> {next_selector!r}"
                )
            selector = next_selector

        raise SessionProtocolError("Profile query exceeded max page count")


def parse_profile_page(reply: bytes) -> ProfilePage:
    """Parse one raw panel reply page for the `?U` family.

    A non-empty page contains up to four profile records followed by `----`.
    The fully empty terminal page is just `*U----`.
    """
    payload = _extract_profile_payload(reply)
    cleaned = payload.rstrip(b"\r\x00")
    if cleaned == PROFILE_PAGE_TERMINATOR:
        return ProfilePage(profiles=[], has_terminal_marker=True, raw_reply=reply)
    if not cleaned:
        raise SessionProtocolError("Empty ?U reply payload")
    if not cleaned.endswith(PROFILE_RECORD_SEPARATOR + PROFILE_PAGE_TERMINATOR):
        raise SessionProtocolError(f"Malformed ?U reply missing terminator: {reply!r}")

    parts = cleaned.split(PROFILE_RECORD_SEPARATOR)
    profiles: list[ProfileRecord] = []
    has_terminal_marker = False

    for part in parts:
        if not part:
            raise SessionProtocolError(f"Malformed ?U reply contained an empty record: {reply!r}")
        if has_terminal_marker:
            raise SessionProtocolError(f"Malformed ?U reply contained data after terminator: {reply!r}")
        if part == PROFILE_PAGE_TERMINATOR:
            has_terminal_marker = True
            continue

        try:
            raw_record = part.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise SessionProtocolError(f"Malformed ?U profile record: {reply!r}") from exc
        profiles.append(_parse_profile_record(raw_record))
        if len(profiles) > PROFILE_MAX_ROWS_PER_PAGE:
            raise SessionProtocolError(
                f"Malformed ?U reply exceeded {PROFILE_MAX_ROWS_PER_PAGE} rows: {reply!r}"
            )

    if not has_terminal_marker:
        raise SessionProtocolError(f"Malformed ?U reply missing terminator: {reply!r}")

    return ProfilePage(profiles=profiles, has_terminal_marker=has_terminal_marker, raw_reply=reply)


def _parse_profile_record(raw_record: str) -> ProfileRecord:
    """Parse one cleartext profile record from a `?U` page.

    The first 49 characters are the older fixed layout. Current captures add a
    later fixed tail before the display name, so we split those pieces out when
    enough data is present.
    """
    if len(raw_record) < PROFILE_LEGACY_MIN_FIXED_WIDTH:
        raise SessionProtocolError(f"Malformed ?U profile record: {raw_record!r}")

    field_30_45 = raw_record[30:46]
    rearm_delay = raw_record[46:49]
    field_49_63 = raw_record[49:64] if len(raw_record) >= PROFILE_CURRENT_FIXED_WIDTH else None

    if len(raw_record) >= PROFILE_CURRENT_FIXED_WIDTH:
        name = raw_record[PROFILE_CURRENT_FIXED_WIDTH:]
    else:
        name = raw_record[49:]

    return ProfileRecord(number=raw_record[0:3], areas_mask=raw_record[3:11], access_areas_mask=raw_record[11:19], output_group=raw_record[19:22], menu_options=raw_record[22:30], field_30_45=field_30_45, rearm_delay=rearm_delay, field_49_63=field_49_63, name=name)


def _next_profile_selector(*, profiles: list[ProfileRecord]) -> str | None:
    """Return the next selector using highest-visible-profile progression."""
    if not profiles:
        return None

    profile_numbers = [int(profile.number, 10) for profile in profiles if profile.number.isdigit()]
    if not profile_numbers:
        return None

    positive_numbers = [value for value in profile_numbers if value > 0]
    if positive_numbers:
        candidate = max(positive_numbers) + 1
    elif max(profile_numbers) == 0:
        candidate = 1
    else:
        return None

    if candidate > PROFILE_MAX_SELECTOR:
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


def _decode_profile_area_mask(mask: str) -> tuple[int, ...]:
    """Decode one 32-area bitmap where each byte is high-bit-first."""
    if len(mask) != 8:
        return ()
    try:
        bytes_ = [int(mask[index:index + 2], 16) for index in range(0, 8, 2)]
    except ValueError:
        return ()

    areas: list[int] = []
    for byte_index, value in enumerate(bytes_):
        for bit_index in range(8):
            if value & (0x80 >> bit_index):
                areas.append(byte_index * 8 + bit_index + 1)
    return tuple(areas)


def _decode_profile_option_byte(menu_options: str, byte_index: int) -> int:
    """Decode one of the 4 visible option bytes from the 8-char hex field."""
    start = byte_index * 2
    end = start + 2
    if len(menu_options) < end:
        return 0
    try:
        return int(menu_options[start:end], 16)
    except ValueError:
        return 0


def _profile_option_bit(menu_options: str, byte_index: int, mask: int) -> bool:
    """Return one known boolean bit from the 4-byte option word."""
    return bool(_decode_profile_option_byte(menu_options, byte_index) & mask)


def _decode_profile_schedule_cell(value: str) -> str | None:
    """Decode one 2-char access schedule cell, preserving wire text."""
    if len(value) != 2 or value == "--":
        return None
    return value


def _decode_profile_tail_cell(field_49_63: str | None, index: int) -> str | None:
    """Decode one trailing 3-char numeric cell beyond `tail_01`."""
    if field_49_63 is None:
        return None
    start = index * 3
    end = start + 3
    if len(field_49_63) < end:
        return None
    return field_49_63[start:end]
