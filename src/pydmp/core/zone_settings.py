"""Stateless `?ZL` zone-settings transaction and reply parsing.

`?ZL` reads one direct zone-settings row, while lowercase `?Zl` behaves more
like a list page. The parser supports both because they share the same record
layout.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SessionProtocolError
from .models import Transaction, payload_required
from .zone_control import normalize_zone_number

ZONE_SETTINGS_RECORD_SEPARATOR = b"\x1e"
ZONE_SETTINGS_REPLY_PREFIXES = (b"*ZL", b"!ZL", b"?ZL", b"*Zl", b"!Zl", b"?Zl")
ZONE_SETTINGS_FIXED_LENGTH = 98
ZONE_SETTINGS_TERMINATOR = b"---"
ZONE_SETTINGS_NAME_MAX_LENGTH = 32
ZONE_SETTINGS_FLAG_VALUES = frozenset("YN")
ZONE_SETTINGS_FLAG54_VALUES = frozenset("FN")
ZONE_SETTINGS_PIR_PULSE_VALUES = frozenset("24")
ZONE_SETTINGS_PIR_SENSITIVITY_VALUES = frozenset("LH")
ZONE_SETTINGS_ENTRY_DELAY_VALUES = frozenset("1234")
ZONE_SETTINGS_NAME_PREFIX_FLAGS = frozenset("YN")


@dataclass(slots=True)
class ZoneSettingsRecord:
    """One decoded zone-settings row from a `?ZL` or `?Zl` reply.

    Known fields are broken out directly. Bytes whose product meaning is still
    open keep neutral names so callers can inspect them without us guessing.
    """

    number: str
    type_code: str
    area: str
    flag_07: str
    nibble_word_08_0f: str
    flag_10: str
    flag_11: str
    flag_12: str
    special_word_13_1a: str
    marker_1b: str
    type_field_1c_1d: str
    disarmed_open_action: str
    disarmed_open_output: str
    disarmed_open_output_mode: str
    disarmed_short_action: str
    disarmed_short_output: str
    disarmed_short_output_mode: str
    armed_open_action: str
    armed_open_output: str
    armed_open_output_mode: str
    armed_short_action: str
    armed_short_output: str
    armed_short_output_mode: str
    entry_delay_number: str
    flag_33: str
    literal_34: str
    flag_35: str
    display_option: str
    flag_37: str
    flag_38: str
    flag_39: str
    reference8: str
    numeric_42: str
    numeric_43: str
    flag_44: str
    flag_45: str
    flag_46: str
    pir_pulse_count: str
    pir_sensitivity: str
    flag_49: str
    filler_4a_4c: str
    type_field_4d_4e: str
    type_field_4f_51: str
    flag_52: str
    numeric_53: str
    flag_54: str
    type5_flag_55: str
    slot_56: str
    reference_mode_57: str
    reference10: str
    name: str
    name_prefix: str = ""

    @property
    def unused(self) -> bool:
        """Return True for the known direct-read unused/default row shape."""
        return self.type_code == "UN" or self.name == "* UNUSED *"


@dataclass(slots=True)
class ZoneSettingsPage:
    """One parsed `?ZL`/`?Zl` reply page."""

    records: list[ZoneSettingsRecord]
    has_terminal_marker: bool
    raw_reply: bytes

    @property
    def short_default(self) -> bool:
        """Return True for the observed bare short form `*ZL---` / `*Zl---`."""
        return self.has_terminal_marker and not self.records


@dataclass(slots=True)
class ZoneSettingsReply:
    """Parsed result of one single-zone `?ZLNNN` transaction."""

    requested_zone: str
    zone: ZoneSettingsRecord | None
    records: list[ZoneSettingsRecord]
    has_terminal_marker: bool
    raw_reply: bytes

    @property
    def found(self) -> bool:
        """Return True when the requested zone was present in the reply."""
        return self.zone is not None

    @property
    def short_default(self) -> bool:
        """Return True for the observed bare short form `*ZL---` / `*Zl---`."""
        return self.has_terminal_marker and not self.records


class TransactionQueryZoneSettings(Transaction):
    """Query settings for one zone with a single `?ZLNNN` request."""

    __slots__ = ("zone_number",)

    def __init__(self, zone: int | str) -> None:
        zone_number = normalize_zone_settings_number(zone)
        self.zone_number = zone_number
        super().__init__(body=f"?ZL{zone_number}", completion=payload_required(), label="query_zone_settings", parser=lambda reply: parse_zone_settings_reply(reply, requested_zone=zone_number))


def normalize_zone_settings_number(zone: int | str) -> str:
    """Normalize a `?ZL`/`?Zl` selector to a 3-digit zone number."""
    if isinstance(zone, int):
        return normalize_zone_number(zone)

    text = str(zone).strip()
    if text.startswith("?ZL") or text.startswith("?Zl"):
        text = text[3:]
    return normalize_zone_number(text)


def parse_zone_settings_reply(
    reply: bytes,
    *,
    requested_zone: int | str,
) -> ZoneSettingsReply:
    """Parse one raw panel reply and select the requested `?ZLNNN` zone."""
    requested = normalize_zone_settings_number(requested_zone)
    page = parse_zone_settings_page(reply)
    matches = [record for record in page.records if record.number == requested]
    if len(matches) > 1:
        raise SessionProtocolError(f"?ZL reply contained duplicate zone {requested}")

    return ZoneSettingsReply(requested_zone=requested, zone=matches[0] if matches else None, records=page.records, has_terminal_marker=page.has_terminal_marker, raw_reply=page.raw_reply)


def parse_zone_settings_page(reply: bytes) -> ZoneSettingsPage:
    """Parse one raw panel reply page for the `?ZL`/`?Zl` family.

    Direct uppercase reads often contain one record with no terminal marker.
    Lowercase list pages can contain one or more records followed by `---`.
    """
    payload = _extract_zone_settings_payload(reply)
    cleaned = payload.rstrip(b"\r\x00")
    if cleaned == ZONE_SETTINGS_TERMINATOR:
        return ZoneSettingsPage(records=[], has_terminal_marker=True, raw_reply=reply)
    if not cleaned:
        raise SessionProtocolError("Empty ?ZL reply payload")

    parts = cleaned.split(ZONE_SETTINGS_RECORD_SEPARATOR)
    trailing_empty_count = 0
    for part in reversed(parts):
        if part != b"":
            break
        trailing_empty_count += 1
    if trailing_empty_count:
        last_non_empty_index = len(parts) - trailing_empty_count - 1
        if last_non_empty_index >= 0 and parts[last_non_empty_index] == ZONE_SETTINGS_TERMINATOR:
            raise SessionProtocolError(
                f"Malformed ?ZL reply contained a separator after terminator: {reply!r}"
            )
        parts = parts[:-trailing_empty_count]

    records: list[ZoneSettingsRecord] = []
    has_terminal_marker = False

    for part in parts:
        if not part:
            raise SessionProtocolError(f"Malformed ?ZL reply contained an empty record: {reply!r}")
        if has_terminal_marker:
            raise SessionProtocolError(
                f"Malformed ?ZL reply contained data after terminator: {reply!r}"
            )
        if part == ZONE_SETTINGS_TERMINATOR:
            has_terminal_marker = True
            continue

        records.append(_parse_zone_settings_record(part))

    return ZoneSettingsPage(records=records, has_terminal_marker=has_terminal_marker, raw_reply=reply)


def _parse_zone_settings_record(raw_record: bytes) -> ZoneSettingsRecord:
    """Parse one fixed-body `?ZL`/`?Zl` row."""
    if len(raw_record) < ZONE_SETTINGS_FIXED_LENGTH:
        raise SessionProtocolError(f"Malformed ?ZL zone-settings record: {raw_record!r}")

    fixed = raw_record[:ZONE_SETTINGS_FIXED_LENGTH]
    name_prefix, name = _split_zone_settings_name_tail(raw_record)
    number_value = _parse_decimal_field(
        fixed[0:3],
        raw_record=raw_record,
        label="zone number",
        minimum=1,
        maximum=999,
    )
    area_value = _parse_decimal_field(
        fixed[5:7],
        raw_record=raw_record,
        label="zone area",
        minimum=0,
        maximum=32,
    )
    disarmed_open_action, disarmed_open_output, disarmed_open_output_mode = (
        _parse_action_group_fields(
            fixed[30:35],
            raw_record=raw_record,
            label="disarmed open",
        )
    )
    disarmed_short_action, disarmed_short_output, disarmed_short_output_mode = (
        _parse_action_group_fields(
            fixed[35:40],
            raw_record=raw_record,
            label="disarmed short",
        )
    )
    armed_open_action, armed_open_output, armed_open_output_mode = _parse_action_group_fields(
        fixed[40:45],
        raw_record=raw_record,
        label="armed open",
    )
    armed_short_action, armed_short_output, armed_short_output_mode = _parse_action_group_fields(
        fixed[45:50],
        raw_record=raw_record,
        label="armed short",
    )

    return ZoneSettingsRecord(
        number=f"{number_value:03d}",
        type_code=_parse_zone_type(fixed[3:5], raw_record=raw_record),
        area=f"{area_value:02d}",
        flag_07=_parse_flag(fixed[7:8], raw_record=raw_record, label="flag 0x07"),
        nibble_word_08_0f=_parse_hex_text(
            fixed[8:16],
            raw_record=raw_record,
            label="nibble word 0x08..0x0f",
        ),
        flag_10=_parse_flag(fixed[16:17], raw_record=raw_record, label="flag 0x10"),
        flag_11=_parse_flag(fixed[17:18], raw_record=raw_record, label="flag 0x11"),
        flag_12=_parse_flag(fixed[18:19], raw_record=raw_record, label="flag 0x12"),
        special_word_13_1a=_decode_ascii(
            fixed[19:27],
            raw_record=raw_record,
            label="special word 0x13..0x1a",
        ),
        marker_1b=_decode_ascii(fixed[27:28], raw_record=raw_record, label="marker 0x1b"),
        type_field_1c_1d=_parse_digit_text(
            fixed[28:30],
            raw_record=raw_record,
            label="type field 0x1c..0x1d",
        ),
        disarmed_open_action=disarmed_open_action,
        disarmed_open_output=disarmed_open_output,
        disarmed_open_output_mode=disarmed_open_output_mode,
        disarmed_short_action=disarmed_short_action,
        disarmed_short_output=disarmed_short_output,
        disarmed_short_output_mode=disarmed_short_output_mode,
        armed_open_action=armed_open_action,
        armed_open_output=armed_open_output,
        armed_open_output_mode=armed_open_output_mode,
        armed_short_action=armed_short_action,
        armed_short_output=armed_short_output,
        armed_short_output_mode=armed_short_output_mode,
        entry_delay_number=_decode_enum(
            fixed[50:51],
            raw_record=raw_record,
            label="entry delay number",
            values=ZONE_SETTINGS_ENTRY_DELAY_VALUES,
        ),
        flag_33=_parse_flag(fixed[51:52], raw_record=raw_record, label="flag 0x33"),
        literal_34=_decode_ascii(fixed[52:53], raw_record=raw_record, label="literal 0x34"),
        flag_35=_parse_flag(fixed[53:54], raw_record=raw_record, label="flag 0x35"),
        display_option=_parse_display_option(
            fixed[54:55],
            raw_record=raw_record,
        ),
        flag_37=_parse_flag(fixed[55:56], raw_record=raw_record, label="flag 0x37"),
        flag_38=_parse_flag(fixed[56:57], raw_record=raw_record, label="flag 0x38"),
        flag_39=_parse_flag(fixed[57:58], raw_record=raw_record, label="flag 0x39"),
        reference8=_decode_ascii(fixed[58:66], raw_record=raw_record, label="reference8"),
        numeric_42=_parse_digit_in_range(
            fixed[66:67],
            raw_record=raw_record,
            label="numeric 0x42",
            minimum=0,
            maximum=3,
        ),
        numeric_43=_parse_digit_in_range(
            fixed[67:68],
            raw_record=raw_record,
            label="numeric 0x43",
            minimum=0,
            maximum=7,
        ),
        flag_44=_parse_flag(fixed[68:69], raw_record=raw_record, label="flag 0x44"),
        flag_45=_parse_flag(fixed[69:70], raw_record=raw_record, label="flag 0x45"),
        flag_46=_parse_flag(fixed[70:71], raw_record=raw_record, label="flag 0x46"),
        pir_pulse_count=_decode_enum(
            fixed[71:72],
            raw_record=raw_record,
            label="PIR pulse count",
            values=ZONE_SETTINGS_PIR_PULSE_VALUES,
        ),
        pir_sensitivity=_decode_enum(
            fixed[72:73],
            raw_record=raw_record,
            label="PIR sensitivity",
            values=ZONE_SETTINGS_PIR_SENSITIVITY_VALUES,
        ),
        flag_49=_parse_flag(fixed[73:74], raw_record=raw_record, label="flag 0x49"),
        filler_4a_4c=_decode_ascii(fixed[74:77], raw_record=raw_record, label="filler 0x4a..0x4c"),
        type_field_4d_4e=_parse_digit_text(
            fixed[77:79],
            raw_record=raw_record,
            label="type field 0x4d..0x4e",
        ),
        type_field_4f_51=_parse_digit_text(
            fixed[79:82],
            raw_record=raw_record,
            label="type field 0x4f..0x51",
        ),
        flag_52=_parse_flag(fixed[82:83], raw_record=raw_record, label="flag 0x52"),
        numeric_53=_parse_digit_in_range(
            fixed[83:84],
            raw_record=raw_record,
            label="numeric 0x53",
            minimum=0,
            maximum=7,
        ),
        flag_54=_decode_enum(
            fixed[84:85],
            raw_record=raw_record,
            label="flag 0x54",
            values=ZONE_SETTINGS_FLAG54_VALUES,
        ),
        type5_flag_55=_decode_ascii(
            fixed[85:86],
            raw_record=raw_record,
            label="type5 flag 0x55",
        ),
        slot_56=_decode_ascii(fixed[86:87], raw_record=raw_record, label="slot 0x56"),
        reference_mode_57=_parse_flag(
            fixed[87:88],
            raw_record=raw_record,
            label="reference mode 0x57",
        ),
        reference10=_decode_ascii(fixed[88:98], raw_record=raw_record, label="reference10"),
        name=name,
        name_prefix=name_prefix,
    )


def _parse_action_group_fields(
    raw_value: bytes,
    *,
    raw_record: bytes,
    label: str,
) -> tuple[str, str, str]:
    """Split one 5-character action cell into action, output, and mode."""
    text = _decode_ascii(raw_value, raw_record=raw_record, label=label)
    action = "none" if text[0] == "-" else text[0]
    output = "none" if text[1:4] == "000" else text[1:4]
    return action, output, text[4]


def _parse_zone_type(raw_value: bytes, *, raw_record: bytes) -> str:
    type_code = _decode_ascii(raw_value, raw_record=raw_record, label="zone type")
    if len(type_code) != 2 or not type_code.isalpha() or not type_code.isupper():
        raise SessionProtocolError(f"Malformed ?ZL zone type: {raw_record!r}")
    return type_code


def _parse_flag(raw_value: bytes, *, raw_record: bytes, label: str) -> str:
    return _decode_enum(
        raw_value,
        raw_record=raw_record,
        label=label,
        values=ZONE_SETTINGS_FLAG_VALUES,
    )


def _parse_display_option(raw_value: bytes, *, raw_record: bytes) -> str:
    display_option = _decode_ascii(raw_value, raw_record=raw_record, label="display option")
    if len(display_option) != 1 or (
        not display_option.isalnum() and display_option != "-"
    ):
        raise SessionProtocolError(f"Malformed ?ZL display option: {raw_record!r}")
    return display_option


def _parse_hex_text(raw_value: bytes, *, raw_record: bytes, label: str) -> str:
    value = _decode_ascii(raw_value, raw_record=raw_record, label=label)
    if any(character not in "0123456789ABCDEF" for character in value):
        raise SessionProtocolError(f"Malformed ?ZL {label}: {raw_record!r}")
    return value


def _parse_digit_text(
    raw_value: bytes,
    *,
    raw_record: bytes,
    label: str,
) -> str:
    value = _decode_ascii(raw_value, raw_record=raw_record, label=label)
    if not value.isdigit():
        raise SessionProtocolError(f"Malformed ?ZL {label}: {raw_record!r}")
    return value


def _parse_digit_in_range(
    raw_value: bytes,
    *,
    raw_record: bytes,
    label: str,
    minimum: int,
    maximum: int,
) -> str:
    value = _parse_digit_text(raw_value, raw_record=raw_record, label=label)
    parsed = int(value, 10)
    if not minimum <= parsed <= maximum:
        raise SessionProtocolError(f"?ZL {label} out of range: {raw_record!r}")
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
    if not minimum <= parsed <= maximum:
        raise SessionProtocolError(f"?ZL {label} out of range: {raw_record!r}")
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
        raise SessionProtocolError(f"Malformed ?ZL {label}: {raw_record!r}")
    return value


def _decode_zone_settings_name(raw_name: bytes, *, raw_record: bytes) -> str:
    name = _decode_ascii(raw_name, raw_record=raw_record, label="zone name")
    if len(name) > ZONE_SETTINGS_NAME_MAX_LENGTH:
        raise SessionProtocolError(f"?ZL zone name too long: {raw_record!r}")
    return name


def _split_zone_settings_name_tail(raw_record: bytes) -> tuple[str, str]:
    """Split the shared 98-byte fixed body from the visible zone name tail.

    Most records place the name directly at offset 98. A later live capture
    also showed a two-byte `-N` prefix before the visible name on one direct
    uppercase row. Preserve that prefix separately and return the cleaned
    visible name.
    """
    raw_name = raw_record[ZONE_SETTINGS_FIXED_LENGTH:]
    if len(raw_name) >= 2:
        prefix = raw_name[:2]
        first = prefix[:1]
        second = prefix[1:2]
        try:
            prefix_text = prefix.decode("ascii")
        except UnicodeDecodeError:
            prefix_text = ""
        if (
            first == b"-"
            and second.decode("ascii", errors="ignore") in ZONE_SETTINGS_NAME_PREFIX_FLAGS
            and raw_name[2:]
        ):
            return prefix_text, _decode_zone_settings_name(raw_name[2:], raw_record=raw_record)

    return "", _decode_zone_settings_name(raw_name, raw_record=raw_record)


def _decode_ascii(raw_value: bytes, *, raw_record: bytes, label: str) -> str:
    try:
        value = raw_value.decode("ascii")
    except UnicodeDecodeError as exc:
        raise SessionProtocolError(f"Malformed ?ZL {label}: {raw_record!r}") from exc

    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in value):
        raise SessionProtocolError(f"Malformed ?ZL {label}: {raw_record!r}")
    return value


def _extract_zone_settings_payload(reply: bytes) -> bytes:
    """Extract the body that follows the `*ZL`/`*Zl` family marker."""
    for marker in ZONE_SETTINGS_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index + len(marker) :]

    raise SessionProtocolError("Reply did not contain a ZL marker")
