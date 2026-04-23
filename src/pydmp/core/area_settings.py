"""Stateless `?Za` area-settings transaction and reply parsing."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SessionProtocolError
from .models import Transaction, payload_required

AREA_SETTINGS_RECORD_SEPARATOR = b"\x1e"
AREA_SETTINGS_REPLY_PREFIXES = (b"*Za", b"!Za", b"?Za")
AREA_SETTINGS_MAX_AREA = 32
AREA_SETTINGS_NAME_MAX_LENGTH = 32
AREA_SETTINGS_FIXED_LENGTH = 28
AREA_SETTINGS_MAX_ROWS_PER_PAGE = 6
AREA_SETTINGS_MAX_VISIBLE_BODY_LENGTH = 0x96
AREA_SETTINGS_TERMINATOR = b"--"
AREA_SETTINGS_YN_VALUES = frozenset("YN")
AREA_SETTINGS_BAD_ZONES_VALUES = frozenset("BFR")
AREA_SETTINGS_DUAL_AUTHORITY_VALUES = frozenset("NRDA")


@dataclass(slots=True)
class AreaSettingsRecord:
    """One decoded area-settings row from a `?Za` reply."""

    number: str
    account: str
    auto_arm: str
    bad_zones: str
    auto_disarm: str
    armed_output: str
    bank_saf: str
    common: str
    dual_authority: str
    arm_first: str
    late_output: str
    late_arm_delay: str
    oc_reports: str
    burg_bell_output: str
    card_plus_pin: str
    name: str


@dataclass(slots=True)
class AreaSettingsPage:
    """One parsed `?Za` reply page."""

    records: list[AreaSettingsRecord]
    has_terminal_marker: bool
    raw_reply: bytes


@dataclass(slots=True)
class AreaSettingsReply:
    """Parsed result of one single-area `?ZaNN` transaction."""

    requested_area: str
    area: AreaSettingsRecord | None
    records: list[AreaSettingsRecord]
    has_terminal_marker: bool
    raw_reply: bytes

    @property
    def found(self) -> bool:
        """Return True when the requested active area was present in the reply."""
        return self.area is not None


class TransactionQueryAreaSettings(Transaction):
    """Query settings for one area with a single `?ZaNN` request."""

    __slots__ = ("area_number",)

    def __init__(self, area: int | str) -> None:
        area_number = normalize_area_settings_number(area)
        self.area_number = area_number
        super().__init__(
            body=f"?Za{area_number}",
            completion=payload_required(),
            label="query_area_settings",
            parser=lambda reply: parse_area_settings_reply(
                reply,
                requested_area=area_number,
            ),
        )


def normalize_area_settings_number(area: int | str) -> str:
    """Normalize a `?Za` area selector to a two-digit area number."""
    if isinstance(area, int):
        if not 1 <= area <= AREA_SETTINGS_MAX_AREA:
            raise ValueError(f"Area number must be 1..{AREA_SETTINGS_MAX_AREA}, got: {area}")
        return f"{area:02d}"

    text = str(area).strip()
    if text.startswith("?Za"):
        text = text[3:]
    if not text:
        raise ValueError("Area number must not be empty")
    if not text.isdigit():
        raise ValueError(f"Malformed area number: {area!r}")

    value = int(text, 10)
    if not 1 <= value <= AREA_SETTINGS_MAX_AREA:
        raise ValueError(f"Area number must be 1..{AREA_SETTINGS_MAX_AREA}, got: {area!r}")
    return f"{value:02d}"


def parse_area_settings_reply(
    reply: bytes,
    *,
    requested_area: int | str,
) -> AreaSettingsReply:
    """Parse one raw panel reply and select the requested `?ZaNN` area."""
    requested = normalize_area_settings_number(requested_area)
    page = parse_area_settings_page(reply)
    matches = [record for record in page.records if record.number == requested]
    if len(matches) > 1:
        raise SessionProtocolError(f"?Za reply contained duplicate area {requested}")

    return AreaSettingsReply(
        requested_area=requested,
        area=matches[0] if matches else None,
        records=page.records,
        has_terminal_marker=page.has_terminal_marker,
        raw_reply=page.raw_reply,
    )


def parse_area_settings_page(reply: bytes) -> AreaSettingsPage:
    """Parse one raw panel reply page for the `?Za` area-settings family."""
    payload = _extract_area_settings_payload(reply)
    cleaned = payload.rstrip(b"\r\x00")
    if cleaned == AREA_SETTINGS_TERMINATOR:
        return AreaSettingsPage(
            records=[],
            has_terminal_marker=True,
            raw_reply=reply,
        )
    if not cleaned:
        raise SessionProtocolError("Empty ?Za reply payload")
    if len(cleaned) > AREA_SETTINGS_MAX_VISIBLE_BODY_LENGTH:
        raise SessionProtocolError(
            f"Malformed ?Za reply exceeded visible body limit "
            f"{AREA_SETTINGS_MAX_VISIBLE_BODY_LENGTH:#x}: {reply!r}"
        )

    parts = cleaned.split(AREA_SETTINGS_RECORD_SEPARATOR)
    records: list[AreaSettingsRecord] = []
    has_terminal_marker = False

    for part in parts:
        if not part:
            raise SessionProtocolError(f"Malformed ?Za reply contained an empty record: {reply!r}")
        if has_terminal_marker:
            raise SessionProtocolError(
                f"Malformed ?Za reply contained data after terminator: {reply!r}"
            )
        if part == AREA_SETTINGS_TERMINATOR:
            has_terminal_marker = True
            continue

        records.append(_parse_area_settings_record(part))
        if len(records) > AREA_SETTINGS_MAX_ROWS_PER_PAGE:
            raise SessionProtocolError(
                f"Malformed ?Za reply exceeded {AREA_SETTINGS_MAX_ROWS_PER_PAGE} rows: {reply!r}"
            )

    if not has_terminal_marker:
        raise SessionProtocolError(f"Malformed ?Za reply missing terminator: {reply!r}")

    return AreaSettingsPage(
        records=records,
        has_terminal_marker=has_terminal_marker,
        raw_reply=reply,
    )


def _parse_area_settings_record(raw_record: bytes) -> AreaSettingsRecord:
    """Parse one fixed-prefix `?Za` area-settings row."""
    if len(raw_record) <= AREA_SETTINGS_FIXED_LENGTH:
        raise SessionProtocolError(f"Malformed ?Za area-settings record: {raw_record!r}")

    number_value = _parse_decimal_field(
        raw_record[0:2],
        raw_record=raw_record,
        label="area number",
        minimum=1,
        maximum=AREA_SETTINGS_MAX_AREA,
    )
    account = _parse_digit_text(raw_record[2:7], raw_record=raw_record, label="account")
    auto_arm = _parse_yn(raw_record[7:8], raw_record=raw_record, label="auto arm")
    bad_zones = _decode_enum(
        raw_record[8:9],
        raw_record=raw_record,
        label="bad zones",
        values=AREA_SETTINGS_BAD_ZONES_VALUES,
    )
    auto_disarm = _parse_yn(raw_record[9:10], raw_record=raw_record, label="auto disarm")
    armed_output = _parse_digit_text(
        raw_record[10:13],
        raw_record=raw_record,
        label="armed output",
    )
    bank_saf = _parse_yn(raw_record[13:14], raw_record=raw_record, label="bank/saf")
    common = _parse_yn(raw_record[14:15], raw_record=raw_record, label="common")
    dual_authority = _decode_enum(
        raw_record[15:16],
        raw_record=raw_record,
        label="dual authority",
        values=AREA_SETTINGS_DUAL_AUTHORITY_VALUES,
    )
    arm_first = _parse_yn(raw_record[16:17], raw_record=raw_record, label="arm first")
    late_output = _parse_digit_text(
        raw_record[17:20],
        raw_record=raw_record,
        label="late output",
    )
    late_arm_delay = _parse_digit_text(
        raw_record[20:23],
        raw_record=raw_record,
        label="late/arm delay",
    )
    oc_reports = _parse_yn(raw_record[23:24], raw_record=raw_record, label="O/C reports")
    burg_bell_output = _parse_digit_text(
        raw_record[24:27],
        raw_record=raw_record,
        label="burg bell output",
    )
    card_plus_pin = _parse_yn(
        raw_record[27:28],
        raw_record=raw_record,
        label="card plus pin",
    )
    name = _decode_area_settings_name(raw_record[28:], raw_record=raw_record)

    return AreaSettingsRecord(
        number=f"{number_value:02d}",
        account=account,
        auto_arm=auto_arm,
        bad_zones=bad_zones,
        auto_disarm=auto_disarm,
        armed_output=armed_output,
        bank_saf=bank_saf,
        common=common,
        dual_authority=dual_authority,
        arm_first=arm_first,
        late_output=late_output,
        late_arm_delay=late_arm_delay,
        oc_reports=oc_reports,
        burg_bell_output=burg_bell_output,
        card_plus_pin=card_plus_pin,
        name=name,
    )


def _parse_yn(raw_value: bytes, *, raw_record: bytes, label: str) -> str:
    return _decode_enum(
        raw_value,
        raw_record=raw_record,
        label=label,
        values=AREA_SETTINGS_YN_VALUES,
    )


def _parse_digit_text(
    raw_value: bytes,
    *,
    raw_record: bytes,
    label: str,
) -> str:
    value = _decode_ascii(raw_value, raw_record=raw_record, label=label)
    if not value.isdigit():
        raise SessionProtocolError(f"Malformed ?Za {label}: {raw_record!r}")
    return value


def _parse_decimal_field(
    raw_value: bytes,
    *,
    raw_record: bytes,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    value = _parse_digit_text(raw_value, raw_record=raw_record, label=label)
    parsed = int(value, 10)
    if parsed < minimum:
        raise SessionProtocolError(f"?Za {label} out of range: {raw_record!r}")
    if parsed > maximum:
        raise SessionProtocolError(f"?Za {label} out of range: {raw_record!r}")
    return parsed


def _decode_enum(
    raw_value: bytes,
    *,
    raw_record: bytes,
    label: str,
    values: frozenset[str],
) -> str:
    value = _decode_ascii(raw_value, raw_record=raw_record, label=label)
    if value not in values:
        raise SessionProtocolError(f"Unexpected ?Za {label} value: {raw_record!r}")
    return value


def _decode_area_settings_name(raw_name: bytes, *, raw_record: bytes) -> str:
    # Bench213 readback trims storage padding on the right; preserve any leading spaces.
    name = _decode_ascii(raw_name, raw_record=raw_record, label="area name").rstrip()
    if not name:
        raise SessionProtocolError(f"Malformed ?Za record missing area name: {raw_record!r}")
    if len(name) > AREA_SETTINGS_NAME_MAX_LENGTH:
        raise SessionProtocolError(
            f"Malformed ?Za area name exceeds {AREA_SETTINGS_NAME_MAX_LENGTH} chars: {raw_record!r}"
        )
    return name


def _decode_ascii(raw_value: bytes, *, raw_record: bytes, label: str) -> str:
    try:
        decoded = raw_value.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise SessionProtocolError(f"Malformed ?Za {label}: {raw_record!r}") from exc

    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in decoded):
        raise SessionProtocolError(f"Malformed ?Za {label}: {raw_record!r}")
    return decoded


def _extract_area_settings_payload(reply: bytes) -> bytes:
    """Extract the body that follows the `*Za`/`!Za`/`?Za` marker."""
    for marker in AREA_SETTINGS_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index + len(marker) :]

    raise SessionProtocolError("Reply did not contain a Za marker")
