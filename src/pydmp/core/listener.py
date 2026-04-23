"""Inbound push listener for the stateless core.

This listener is intentionally independent from the command-session manager.
It accepts panel-initiated push connections, normalizes clear and secure
(`!!S`) push traffic into one shared event model, and ACKs traffic before
dispatching callbacks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
import re
import os

from ..const.strings import SYSTEM_MESSAGES
from .errors import ListenerConfigurationError, ListenerProtocolError
from .secure_s import (
    SECURE_S_FRAME_TYPE_DATA,
    SECURE_S_FRAME_TYPE_SETUP,
    SECURE_S_PREFIX,
    SecureSReplyState,
    build_secure_s_push_ack_frame,
    build_secure_s_setup_reply_frame,
    parse_secure_s_frame,
    peek_secure_s_frame_length,
)

# Serial 3 push bodies delimit fields with a literal backslash byte (0x5C).
# The Python string literal "\\" is one backslash, matching the on-wire byte.
SERIAL3_FIELD_DELIMITER = "\\"

# These small allowlists let us parse the obvious event shapes confidently
# while leaving surprising traffic in raw form for later analysis.
ZONE_EVENT_TYPE_CODES = frozenset({"BL", "FI", "BU", "SV", "PN", "EM", "A1", "A2", "CO", "VA", "HU"})
ARMING_EVENT_TYPE_CODES = frozenset({"OP", "CL", "LA"})
ACCESS_EVENT_TYPE_CODES = frozenset({"DA", "AA", "IA", "IT", "AP", "IC", "IL", "WP", "IN"})
REALTIME_EVENT_TYPE_CODES = frozenset({"DO", "DC", "HO", "FO", "ON", "OF", "PL", "TP", "MO"})
USER_CODE_EVENT_TYPE_CODES = frozenset({"AD", "CH", "DE", "IN"})
SCHEDULE_NAMED_TYPE_CODES = frozenset({"PE", "TE", "PR", "SE", "S1", "S2", "S3", "S4"})


class PushTransportMode(str, Enum):
    """Wire-level push transport modes seen on the listener lanes."""

    CLEAR = "clear"
    SECURE_S = "secure_s"


@dataclass(slots=True)
class PushEvent:
    """Raw push event plus optional code-specific parsed data."""

    account: str
    definition: str
    fields: list[str]
    raw: str
    parsed: object | None = None
    parser_name: str | None = None


@dataclass(slots=True)
class PushParsedTaggedEvent:
    """Parsed data for one tag-oriented `Z*` push event."""

    event_code: str | None
    type_code: str | None
    event_qualifier: str | None
    area: str | None
    area_name: str | None
    zone: str | None
    zone_name: str | None
    user: str | None
    user_name: str | None
    target_user: str | None
    target_user_name: str | None
    device: str | None
    device_name: str | None
    path_number: str | None
    path_transport: str | None
    path_role: str | None
    system_code: str | None
    system_text: str | None


@dataclass(slots=True)
class PushParsedZoneEvent:
    """Parsed data for zone-style event families like `Zc`, `Zx`, and `Zr`."""

    event_code: str | None
    type_code: str | None
    target_kind: str | None
    zone: str | None
    zone_name: str | None
    device: str | None
    device_name: str | None
    area: str | None
    area_name: str | None
    actor_user: str | None
    actor_user_name: str | None


@dataclass(slots=True)
class PushParsedAccessEvent:
    """Parsed data for access / keypad events like `Zj`."""

    event_code: str | None
    type_code: str | None
    device: str | None
    device_name: str | None
    actor_user: str | None
    actor_user_name: str | None
    entered_code: str | None


@dataclass(slots=True)
class PushParsedScheduleEvent:
    """Parsed data for schedule events like `Zl`."""

    event_code: str | None
    type_code: str | None
    schedule_name: str | None
    open_time: str | None
    open_day: str | None
    close_time: str | None
    close_day: str | None
    actor_user: str | None
    actor_user_name: str | None


@dataclass(slots=True)
class PushParsedUserCodeEvent:
    """Parsed data for user-code events like `Zu`."""

    event_code: str | None
    type_code: str | None
    subject_user: str | None
    subject_user_name: str | None
    actor_user: str | None
    actor_user_name: str | None
    protected_hex: str | None


@dataclass(slots=True)
class PushParsedCheckinEvent:
    """Parsed data for a host-output `s070` check-in frame."""

    interval_minutes: int | None


@dataclass(slots=True)
class PushSpecialFrame:
    """Structured listener notice for non-event conditions."""

    kind: str
    interval_minutes: int | None = None
    raw: str | None = None
    detail: str | None = None


@dataclass(slots=True)
class PushMessage:
    """One inbound push frame after normalization."""

    transport_mode: PushTransportMode
    raw_frame: bytes
    clear_frame: bytes
    normalized_frame: bytes
    account: str | None
    event: PushEvent | None
    special: PushSpecialFrame | None = None
    ack_frame: bytes | None = None
    had_stx: bool = False
    had_nuls: bool = False
    had_trailing_cr: bool = False
    wrapper_crc_hex: str | None = None
    wrapper_crc_calc: str | None = None
    wrapper_crc_valid: bool | None = None
    route_token: str | None = None
    delivery_field: str | None = None


@dataclass(slots=True)
class InboundAction:
    """All output generated while consuming one chunk of inbound bytes."""

    outbound_frames: list[bytes] = field(default_factory=list)
    messages: list[PushMessage] = field(default_factory=list)
    close_connection: bool = False


@dataclass(slots=True)
class _PushConnectionState:
    buffer: bytes = b""
    secure_passphrase: str | None = None
    secure_reply_state: SecureSReplyState | None = None


Callback = Callable[[PushMessage], Awaitable[None] | None]
PushEventParser = Callable[[str, bytes, str], object | None]


def _compute_host_output_crc(payload: bytes) -> int:
    """Compute the CRC used by host-output wrapped push frames."""
    crc = 0
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def _is_ascii_hex(value: bytes) -> bool:
    """Return `True` when a byte string is made only of ASCII hex digits."""
    return bool(value) and all(chr(byte) in "0123456789ABCDEFabcdef" for byte in value)


def _normalize_clear_frame(frame_bytes: bytes) -> tuple[bytes, bool, bool, bool]:
    """Strip transport noise so the parser sees one stable clear payload.

    The listener keeps track of what was removed so callers can still inspect
    whether STX, NUL padding, or a trailing carriage return were present.
    """
    without_nuls = frame_bytes.replace(b"\x00", b"")
    had_nuls = without_nuls != frame_bytes
    had_stx = without_nuls.startswith(b"\x02")
    normalized = without_nuls[1:] if had_stx else without_nuls
    had_trailing_cr = normalized.endswith(b"\r")
    if had_trailing_cr:
        normalized = normalized[:-1]
    return normalized, had_stx, had_nuls, had_trailing_cr


def _extract_account_field(normalized_frame: bytes) -> str:
    """Pull the 5-character account field from a normalized clear frame."""
    if len(normalized_frame) < 11:
        return ""
    account_field = normalized_frame[6:11]
    if not all(byte == 0x20 or 0x30 <= byte <= 0x39 for byte in account_field):
        return ""
    return account_field.decode("ascii", errors="ignore")


def _build_clear_ack(account: str) -> bytes:
    """Build the plain Serial 3 ACK used on clear listener lanes."""
    digits = str(account).strip()
    if not digits.isdigit() or not 1 <= len(digits) <= 5:
        raise ValueError(f"Account must be 1..5 digits: {account!r}")
    return b"\x02" + digits.rjust(5).encode("ascii") + b"\x06\r"


def _parse_host_output_wrapper(normalized_frame: bytes) -> dict[str, str | bool | None]:
    """Parse the optional host-output wrapper that appears ahead of some pushes.

    When present, this wrapper adds its own CRC and routing fields before the
    actual Serial 3 event body.
    """
    info: dict[str, str | bool | None] = {
        "wrapper_crc_hex": None,
        "wrapper_crc_calc": None,
        "wrapper_crc_valid": None,
        "route_token": None,
        "delivery_field": None,
    }
    if len(normalized_frame) < 12:
        return info

    wrapper_crc = normalized_frame[:4]
    account_field = normalized_frame[6:11]
    if not _is_ascii_hex(wrapper_crc):
        return info
    if not all(byte == 0x20 or 0x30 <= byte <= 0x39 for byte in account_field):
        return info
    if normalized_frame[11] != 0x20:
        return info

    wrapper_crc_hex = wrapper_crc.decode("ascii", errors="ignore").upper()
    wrapper_crc_calc = f"{_compute_host_output_crc(normalized_frame[4:] + b'\r'):04X}"
    delivery_field: str | None = None
    if len(normalized_frame) >= 18 and normalized_frame[12:13] == b"&":
        candidate = normalized_frame[13:18]
        if all(0x30 <= byte <= 0x39 for byte in candidate):
            delivery_field = "&" + candidate.decode("ascii")

    info["wrapper_crc_hex"] = wrapper_crc_hex
    info["wrapper_crc_calc"] = wrapper_crc_calc
    info["wrapper_crc_valid"] = wrapper_crc_hex == wrapper_crc_calc
    info["route_token"] = normalized_frame[4:6].decode("ascii", errors="ignore")
    info["delivery_field"] = delivery_field
    return info


def _find_serial3_event_offset(normalized_frame: bytes) -> int | None:
    """Find the start of the `Z*` event body inside a normalized frame."""
    match = re.search(rb"Z[a-z]\\\d{3}", normalized_frame)
    if match is None:
        return None
    return match.start()


def _decode_ascii_field(value: bytes | None) -> str | None:
    if not value:
        return None
    text = value.decode("ascii", errors="ignore").strip()
    return text or None


def _extract_type_code(payload: bytes) -> str | None:
    match = re.match(rb"^[A-Za-z]{2}\\\d{3}(?:\\t|\t)\s*\"(?P<op>[A-Z0-9]{2})\\", payload)
    if not match:
        return None
    return _decode_ascii_field(match.group("op"))


def _extract_event_code(payload: bytes) -> str | None:
    match = re.match(rb"^[A-Za-z]{2}\\(?P<code>\d{3})(?:\\|$)", payload)
    if not match:
        return None
    return _decode_ascii_field(match.group("code"))


def _extract_system_code(payload: bytes, definition: str) -> str | None:
    if definition == "Zs":
        match = re.search(rb"^Zs\\\d{3}(?:\\t|\t)\s*(?P<code>\d{3})(?:\\|$)", payload)
        if match:
            return _decode_ascii_field(match.group("code"))
    system_code, _ = _extract_tag(payload, b"s", 3)
    return system_code


def _extract_tag(payload: bytes, tag: bytes, width: int) -> tuple[str | None, str | None]:
    """Extract one tagged id/name pair like `\\a 003\"AREA NAME\\`."""
    pattern = re.compile(
        rb"\\" + re.escape(tag) + rb"\s*(?P<id>\d{"
        + str(width).encode("ascii")
        + rb"})(?:\"(?P<name>[^\\]{0,64})\\)?"
    )
    match = pattern.search(payload)
    if not match:
        return None, None
    return _decode_ascii_field(match.group("id")), _decode_ascii_field(match.group("name"))


def _extract_segment_body(payload: bytes, tag: bytes) -> bytes | None:
    match = re.search(rb"\\" + re.escape(tag) + rb"(?P<body>[^\\]{0,128})", payload)
    if not match:
        return None
    return match.group("body")


def _extract_simple_segment_body(payload: bytes, tag: bytes) -> bytes | None:
    match = re.search(rb"\\" + re.escape(tag) + rb"(?![a-z])(?P<body>[^\\]{0,128})", payload)
    if not match:
        return None
    return match.group("body")


def _decode_segment_body(value: bytes | None) -> str | None:
    if not value:
        return None
    text = value.decode("ascii", errors="ignore").strip()
    return text or None


def _strip_optional_quote(value: str | None) -> str | None:
    if value is None:
        return None
    return value[1:] if value.startswith('"') else value


def _normalize_hex(value: bytes | None) -> str | None:
    text = _decode_segment_body(value)
    if text is None or re.fullmatch(r"[0-9A-Fa-f]+", text) is None:
        return None
    return text.upper()


def _extract_event_qualifier(payload: bytes) -> str | None:
    return _strip_optional_quote(_decode_segment_body(_extract_simple_segment_body(payload, b"e")))


def _parse_path_info(payload: bytes) -> tuple[str | None, str | None, str | None]:
    raw = _decode_segment_body(_extract_simple_segment_body(payload, b"c"))
    if raw is None:
        return None, None, None
    if '"' in raw:
        number, path_flags = raw.split('"', 1)
    else:
        number, path_flags = raw[:2], raw[2:]
    number = number.strip() or None
    path_flags = path_flags.strip()
    if number is None or re.fullmatch(r"\d{2}", number) is None:
        return None, None, None
    if len(path_flags) != 2:
        return number, None, None
    return number, path_flags[0], path_flags[1]


def _extract_entered_code(payload: bytes) -> str | None:
    raw = _strip_optional_quote(_decode_segment_body(_extract_segment_body(payload, b"eu")))
    if raw is None or raw.isdigit() is False:
        return None
    return raw


def _is_schedule_type_code(type_code: str | None) -> bool:
    if type_code is None:
        return False
    return type_code in SCHEDULE_NAMED_TYPE_CODES or re.fullmatch(r"\d{2}", type_code) is not None


def _classify_zone_target(zone: str | None, device: str | None) -> str | None:
    if zone and device:
        return "mixed"
    if zone:
        return "zone"
    if device:
        return "device"
    return None


def _parse_time_day_segment(value: bytes | None) -> tuple[str | None, str | None]:
    text = _decode_segment_body(value)
    if text is None:
        return None, None
    if '"' not in text:
        return text, None
    time_text, day_text = text.split('"', 1)
    return time_text or None, day_text or None


def _parse_tagged_push_event(_account: str, payload: bytes, _raw: str) -> PushParsedTaggedEvent:
    """Parse the flexible tagged shape used by `Zq` and `Zs`."""
    definition = payload[:2].decode("ascii", errors="replace")
    event_code = _extract_event_code(payload)
    type_code = _extract_type_code(payload)
    area, area_name = _extract_tag(payload, b"a", 3)
    zone, zone_name = _extract_tag(payload, b"z", 3)
    user, user_name = _extract_tag(payload, b"u", 5)
    target_user, target_user_name = _extract_tag(payload, b"um", 5)
    device, device_name = _extract_tag(payload, b"v", 3)
    system_code = _extract_system_code(payload, definition)
    event_qualifier = _extract_event_qualifier(payload)
    path_number, path_transport, path_role = _parse_path_info(payload)
    if definition == "Zq":
        if event_code is None or type_code not in ARMING_EVENT_TYPE_CODES or area is None:
            return None
    elif definition == "Zs":
        if system_code is None:
            return None
    return PushParsedTaggedEvent(
        event_code=event_code,
        type_code=type_code,
        event_qualifier=event_qualifier,
        area=area,
        area_name=area_name,
        zone=zone,
        zone_name=zone_name,
        user=user,
        user_name=user_name,
        target_user=target_user,
        target_user_name=target_user_name,
        device=device,
        device_name=device_name,
        path_number=path_number,
        path_transport=path_transport,
        path_role=path_role,
        system_code=system_code,
        system_text=SYSTEM_MESSAGES.get(system_code) if system_code else None,
    )


def _parse_zone_push_event(_account: str, payload: bytes, _raw: str) -> PushParsedZoneEvent:
    """Parse zone-style event families such as `Zc`, `Zx`, `Zr`, and `Zt`."""
    definition = payload[:2].decode("ascii", errors="replace")
    event_code = _extract_event_code(payload)
    type_code = _extract_type_code(payload)
    zone, zone_name = _extract_tag(payload, b"z", 3)
    device, device_name = _extract_tag(payload, b"v", 3)
    area, area_name = _extract_tag(payload, b"a", 3)
    actor_user, actor_user_name = _extract_tag(payload, b"u", 5)
    target_kind = _classify_zone_target(zone, device)
    allowed_types = REALTIME_EVENT_TYPE_CODES if definition == "Zc" else ZONE_EVENT_TYPE_CODES
    if event_code is None or type_code not in allowed_types or target_kind is None:
        return None
    return PushParsedZoneEvent(
        event_code=event_code,
        type_code=type_code,
        target_kind=target_kind,
        zone=zone,
        zone_name=zone_name,
        device=device,
        device_name=device_name,
        area=area,
        area_name=area_name,
        actor_user=actor_user,
        actor_user_name=actor_user_name,
    )


def _parse_access_push_event(_account: str, payload: bytes, _raw: str) -> PushParsedAccessEvent:
    """Parse keypad and access-style pushes such as `Zj`."""
    event_code = _extract_event_code(payload)
    type_code = _extract_type_code(payload)
    device, device_name = _extract_tag(payload, b"v", 3)
    actor_user, actor_user_name = _extract_tag(payload, b"u", 5)
    entered_code = _extract_entered_code(payload)
    if event_code is None or type_code not in ACCESS_EVENT_TYPE_CODES or device is None:
        return None
    return PushParsedAccessEvent(
        event_code=event_code,
        type_code=type_code,
        device=device,
        device_name=device_name,
        actor_user=actor_user,
        actor_user_name=actor_user_name,
        entered_code=entered_code,
    )


def _parse_schedule_push_event(_account: str, payload: bytes, _raw: str) -> PushParsedScheduleEvent:
    """Parse schedule pushes such as `Zl`."""
    event_code = _extract_event_code(payload)
    type_code = _extract_type_code(payload)
    schedule_name = _strip_optional_quote(_decode_segment_body(_extract_simple_segment_body(payload, b"n")))
    open_time, open_day = _parse_time_day_segment(_extract_segment_body(payload, b"io"))
    close_time, close_day = _parse_time_day_segment(_extract_segment_body(payload, b"ic"))
    actor_user, actor_user_name = _extract_tag(payload, b"u", 5)
    if (
        event_code is None
        or _is_schedule_type_code(type_code) is False
        or all(
            value is None
            for value in (schedule_name, open_time, close_time, actor_user)
        )
    ):
        return None
    return PushParsedScheduleEvent(
        event_code=event_code,
        type_code=type_code,
        schedule_name=schedule_name,
        open_time=open_time,
        open_day=open_day,
        close_time=close_time,
        close_day=close_day,
        actor_user=actor_user,
        actor_user_name=actor_user_name,
    )


def _parse_user_code_push_event(_account: str, payload: bytes, _raw: str) -> PushParsedUserCodeEvent:
    """Parse user-code administration pushes such as `Zu`."""
    event_code = _extract_event_code(payload)
    type_code = _extract_type_code(payload)
    subject_user, subject_user_name = _extract_tag(payload, b"um", 5)
    actor_user, actor_user_name = _extract_tag(payload, b"u", 5)
    protected_hex = _normalize_hex(_extract_segment_body(payload, b"P"))
    if (
        event_code is None
        or type_code not in USER_CODE_EVENT_TYPE_CODES
        or all(value is None for value in (subject_user, actor_user))
    ):
        return None
    return PushParsedUserCodeEvent(
        event_code=event_code,
        type_code=type_code,
        subject_user=subject_user,
        subject_user_name=subject_user_name,
        actor_user=actor_user,
        actor_user_name=actor_user_name,
        protected_hex=protected_hex,
    )


def _parse_checkin_s070_event(_account: str, _payload: bytes, raw: str) -> PushParsedCheckinEvent:
    """Parse the simple `s070` check-in push."""
    match = re.search(r"s070(?P<interval>\d{4})?$", raw.strip())
    interval_text = match.group("interval") if match else None
    return PushParsedCheckinEvent(
        interval_minutes=int(interval_text) if interval_text is not None else None
    )


DEFAULT_PUSH_EVENT_PARSERS: dict[str, PushEventParser] = {
    "Za": _parse_zone_push_event,
    "Zc": _parse_zone_push_event,
    "Zj": _parse_access_push_event,
    "Zl": _parse_schedule_push_event,
    "Zq": _parse_tagged_push_event,
    "Zr": _parse_zone_push_event,
    "Zs": _parse_tagged_push_event,
    "Zt": _parse_zone_push_event,
    "Zu": _parse_user_code_push_event,
    "Zx": _parse_zone_push_event,
    "Zy": _parse_zone_push_event,
    "s070": _parse_checkin_s070_event,
}


def _extract_push_event_payload(normalized_frame: bytes) -> tuple[str, bytes, str] | None:
    """Extract either a `Z*` event body or a plain `s070` check-in body."""
    offset = _find_serial3_event_offset(normalized_frame)
    if offset is not None:
        payload = normalized_frame[offset:]
        raw = payload.decode("ascii", errors="replace")
        return raw[:2], payload, raw

    text = normalized_frame.decode("ascii", errors="ignore")
    match = re.search(r"s070\d{0,4}\s*$", text)
    if match is None:
        return None
    raw = match.group(0).strip()
    payload = raw.encode("ascii")
    return "s070", payload, raw


def parse_push_event(
    account: str | None,
    normalized_frame: bytes,
    *,
    event_parsers: dict[str, PushEventParser] | None = None,
) -> PushEvent | None:
    """Parse one normalized clear push frame into a raw event plus optional parsed data.

    If there is no registered parser for the event definition, callers still
    get the raw event shell so new event families can be captured and studied
    without changing listener behavior first.
    """
    extracted = _extract_push_event_payload(normalized_frame)
    if extracted is None:
        return None

    definition, payload, raw = extracted
    parser = (event_parsers or DEFAULT_PUSH_EVENT_PARSERS).get(definition)
    parsed: object | None = None
    parser_name: str | None = None
    if parser is not None:
        parsed = parser((account or "").strip(), payload, raw)
        parser_name = getattr(parser, "__name__", parser.__class__.__name__)

    return PushEvent(
        account=(account or "").strip(),
        definition=definition,
        fields=raw.split(SERIAL3_FIELD_DELIMITER),
        raw=raw,
        parsed=parsed,
        parser_name=parser_name,
    )


def _build_push_message(
    *,
    transport_mode: PushTransportMode,
    raw_frame: bytes,
    clear_frame: bytes,
    ack_frame: bytes | None = None,
    event_parsers: dict[str, PushEventParser] | None = None,
) -> PushMessage:
    """Build the final listener message object for one inbound frame."""
    normalized_frame, had_stx, had_nuls, had_trailing_cr = _normalize_clear_frame(clear_frame)
    account_field = _extract_account_field(normalized_frame)
    account = account_field.strip() or None
    wrapper_info = _parse_host_output_wrapper(normalized_frame)
    event = parse_push_event(account, normalized_frame, event_parsers=event_parsers)

    return PushMessage(
        transport_mode=transport_mode,
        raw_frame=raw_frame,
        clear_frame=clear_frame,
        normalized_frame=normalized_frame,
        account=account,
        event=event,
        ack_frame=ack_frame,
        had_stx=had_stx,
        had_nuls=had_nuls,
        had_trailing_cr=had_trailing_cr,
        wrapper_crc_hex=wrapper_info["wrapper_crc_hex"],  # type: ignore[assignment]
        wrapper_crc_calc=wrapper_info["wrapper_crc_calc"],  # type: ignore[assignment]
        wrapper_crc_valid=wrapper_info["wrapper_crc_valid"],  # type: ignore[assignment]
        route_token=wrapper_info["route_token"],  # type: ignore[assignment]
        delivery_field=wrapper_info["delivery_field"],  # type: ignore[assignment]
    )


def _build_mode_mismatch_message(
    *,
    expected_secure: bool,
    raw_frame: bytes,
) -> PushMessage:
    """Build a listener notice for clear-vs-secure mode mismatches."""
    observed_mode = (
        PushTransportMode.SECURE_S
        if raw_frame.startswith(SECURE_S_PREFIX)
        else PushTransportMode.CLEAR
    )
    detail = (
        "Received secure !!S push traffic on a clear-only listener"
        if not expected_secure
        else "Received clear push traffic on a secure-only listener"
    )
    return PushMessage(
        transport_mode=observed_mode,
        raw_frame=raw_frame,
        clear_frame=raw_frame,
        normalized_frame=raw_frame,
        account=None,
        event=None,
        special=PushSpecialFrame(
            kind="listener_mode_mismatch",
            raw=raw_frame.decode("ascii", errors="replace"),
            detail=detail,
        ),
    )


def _build_secure_passphrase_mismatch_message(raw_frame: bytes) -> PushMessage:
    """Build a listener notice for secure traffic that matched no passphrase."""
    return PushMessage(
        transport_mode=PushTransportMode.SECURE_S,
        raw_frame=raw_frame,
        clear_frame=raw_frame,
        normalized_frame=raw_frame,
        account=None,
        event=None,
        special=PushSpecialFrame(
            kind="secure_passphrase_mismatch",
            raw=raw_frame.decode("ascii", errors="replace"),
            detail="Secure !!S frame did not match any configured passphrase",
        ),
    )


def _is_bare_s070_checkin(message: PushMessage) -> bool:
    event = message.event
    if event is None or event.definition != "s070":
        return False
    return bool(
        re.match(
            rb"^[0-9A-Fa-f]{4}..[ 0-9]{5} s070\d{0,4}\s*$",
            message.normalized_frame,
        )
    )


def _choose_even_server_seq() -> int:
    return int.from_bytes(os.urandom(2), "little") & 0xFFFE


def _should_ack_push_message(message: PushMessage) -> bool:
    """Decide whether the listener should ACK this message.

    We only ACK frames that exposed a usable account field. Bare `s070`
    check-ins are allowed through even though they do not carry a full parsed
    event body. Wrapped frames with a bad wrapper CRC are intentionally not
    ACKed.
    """
    if not message.account:
        return False
    if _is_bare_s070_checkin(message):
        return True
    if message.wrapper_crc_hex is not None and message.wrapper_crc_valid is False:
        return False
    return True


class ListenerProfilePush:
    """Inbound push profile for the listener lanes used by `pydmp`.

    This profile is mode-selecting, not auto-detecting:

    - with no configured passphrase, it accepts only clear push frames
    - with one or more configured passphrases, it accepts only secure `!!S`
      push frames

    Wrong-mode traffic is intentionally not ACKed.
    """

    def __init__(self, *, secure_passphrases: Iterable[str] | None = None):
        self._secure_passphrases = [
            str(passphrase)
            for passphrase in (secure_passphrases or [])
            if str(passphrase)
        ]
        self._event_parsers: dict[str, PushEventParser] = dict(DEFAULT_PUSH_EVENT_PARSERS)

    def register_event_parser(self, definition: str, parser: PushEventParser) -> None:
        """Register or replace the parser for one event definition."""
        self._event_parsers[str(definition)] = parser

    def remove_event_parser(self, definition: str) -> None:
        """Remove the parser for one event definition."""
        self._event_parsers.pop(str(definition), None)

    def create_connection_state(self) -> _PushConnectionState:
        """Create the per-socket state bucket used while bytes are arriving."""
        return _PushConnectionState()

    def feed_data(self, state: _PushConnectionState, chunk: bytes) -> InboundAction:
        """Consume a new chunk of socket bytes and emit ACKs/messages.

        This method is incremental on purpose. A panel may split one push
        frame across multiple TCP reads, so we keep a buffer until we have a
        whole frame.
        """
        state.buffer += chunk
        action = InboundAction()

        if self._secure_passphrases:
            if (
                state.buffer
                and not state.buffer.startswith(SECURE_S_PREFIX)
                and not SECURE_S_PREFIX.startswith(state.buffer)
            ):
                action.messages.append(
                    _build_mode_mismatch_message(
                        expected_secure=True,
                        raw_frame=state.buffer,
                    )
                )
                state.buffer = b""
                action.close_connection = True
                return action
        elif state.buffer.startswith(SECURE_S_PREFIX):
            action.messages.append(
                _build_mode_mismatch_message(
                    expected_secure=False,
                    raw_frame=state.buffer,
                )
            )
            state.buffer = b""
            action.close_connection = True
            return action

        while state.buffer:
            if self._secure_passphrases:
                # Secure listeners consume one framed `!!S` message at a time.
                secure_action = self._consume_secure_frame(state)
                if secure_action is None:
                    break
                action.outbound_frames.extend(secure_action.outbound_frames)
                action.messages.extend(secure_action.messages)
                if secure_action.close_connection:
                    action.close_connection = True
                    break
                continue

            # Clear listener lanes treat carriage return as the frame boundary.
            if b"\r" not in state.buffer:
                break

            raw_frame, state.buffer = state.buffer.split(b"\r", 1)
            if not raw_frame:
                continue

            ack_frame = None
            message = _build_push_message(
                transport_mode=PushTransportMode.CLEAR,
                raw_frame=raw_frame,
                clear_frame=raw_frame,
                event_parsers=self._event_parsers,
            )
            if _should_ack_push_message(message):
                ack_frame = _build_clear_ack(message.account)
                message.ack_frame = ack_frame
                action.outbound_frames.append(ack_frame)
            action.messages.append(message)

        return action

    def _consume_secure_frame(self, state: _PushConnectionState) -> InboundAction | None:
        """Consume one complete secure `!!S` frame when enough bytes are buffered."""
        if not self._secure_passphrases and state.secure_passphrase is None:
            raise ListenerConfigurationError(
                "Secure !!S push traffic requires at least one configured passphrase"
            )

        passphrase = state.secure_passphrase
        frame_length: int | None = None

        if passphrase is None:
            candidate = self._select_secure_passphrase(state.buffer)
            if candidate is None:
                if len(state.buffer) >= len(SECURE_S_PREFIX) + 16:
                    raw_frame = state.buffer
                    state.buffer = b""
                    return InboundAction(
                        messages=[_build_secure_passphrase_mismatch_message(raw_frame)],
                        close_connection=True,
                    )
                return None
            passphrase, frame_length = candidate
        else:
            frame_length = peek_secure_s_frame_length(passphrase, state.buffer)

        if frame_length is None or len(state.buffer) < frame_length:
            return None

        frame_bytes = state.buffer[:frame_length]
        state.buffer = state.buffer[frame_length:]

        frame = parse_secure_s_frame(passphrase, frame_bytes)
        state.secure_passphrase = passphrase
        action = InboundAction()

        if frame.frame_type == SECURE_S_FRAME_TYPE_SETUP:
            reply_frame, reply_state = build_secure_s_setup_reply_frame(passphrase, frame, server_seq=_choose_even_server_seq())
            state.secure_reply_state = reply_state
            action.outbound_frames.append(reply_frame)
            return action

        if frame.frame_type != SECURE_S_FRAME_TYPE_DATA:
            raise ListenerProtocolError(
                f"Unsupported secure push frame type: 0x{frame.frame_type:02X}"
            )
        if state.secure_reply_state is None:
            raise ListenerProtocolError("Secure push data arrived before secure setup completed")

        message = _build_push_message(
            transport_mode=PushTransportMode.SECURE_S,
            raw_frame=frame_bytes,
            clear_frame=frame.payload,
            event_parsers=self._event_parsers,
        )
        if not message.account:
            raise ListenerProtocolError("Secure push payload did not expose a valid account field")

        if _should_ack_push_message(message):
            ack_frame = build_secure_s_push_ack_frame(passphrase, state.secure_reply_state, account=message.account, incoming_push=frame)
            message.ack_frame = ack_frame
            action.outbound_frames.append(ack_frame)
        action.messages.append(message)
        return action

    def _select_secure_passphrase(self, buffer: bytes) -> tuple[str, int] | None:
        """Find the configured passphrase that can successfully parse the buffered frame."""
        if len(buffer) < len(SECURE_S_PREFIX) + 16:
            return None
        if not buffer.startswith(SECURE_S_PREFIX):
            raise ListenerProtocolError("Secure listener buffer did not start with the !!S prefix")

        pending: tuple[str, int] | None = None
        for passphrase in self._secure_passphrases:
            try:
                frame_length = peek_secure_s_frame_length(passphrase, buffer)
                if frame_length is None:
                    continue
                if len(buffer) < frame_length:
                    if pending is None:
                        pending = (passphrase, frame_length)
                    continue
                parse_secure_s_frame(passphrase, buffer[:frame_length])
                return passphrase, frame_length
            except Exception:
                continue
        return pending


class DMPPushListener:
    """Async TCP push listener for the stateless core.

    The listener accepts inbound push sockets, delegates byte parsing to a
    `ListenerProfilePush`, then forwards fully built `PushMessage` objects to
    registered callbacks.
    """

    def __init__(
        self,
        *,
        listen_host: str = "0.0.0.0",
        listen_port: int = 8001,
        profile: ListenerProfilePush | None = None,
    ):
        self._listen_host = str(listen_host)
        self._listen_port = int(listen_port)
        self._profile = profile or ListenerProfilePush()
        self._server: asyncio.base_events.Server | None = None
        self._callbacks: set[Callback] = set()
        self._client_writers: set[asyncio.StreamWriter] = set()

    def register_callback(self, callback: Callback) -> None:
        """Register a callback that will receive every parsed push message."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callback) -> None:
        """Remove a previously registered callback."""
        self._callbacks.discard(callback)

    async def start(self) -> None:
        """Start the TCP listener if it is not already running."""
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._handle_client, self._listen_host, self._listen_port)

    async def stop(self) -> None:
        """Stop the server and close any active client sockets."""
        server = self._server
        self._server = None
        if server is not None:
            server.close()
            await server.wait_closed()

        writers = list(self._client_writers)
        for writer in writers:
            writer.close()
        if writers:
            await asyncio.gather(*(writer.wait_closed() for writer in writers), return_exceptions=True)

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Read bytes from one client socket until it closes or the profile ends it."""
        state = self._profile.create_connection_state()
        self._client_writers.add(writer)
        try:
            while not reader.at_eof():
                chunk = await reader.read(4096)
                if not chunk:
                    break
                action = self._profile.feed_data(state, chunk)
                for outbound_frame in action.outbound_frames:
                    writer.write(outbound_frame)
                if action.outbound_frames:
                    await writer.drain()
                # Dispatch after ACK work so the panel is not kept waiting by
                # slow application callbacks.
                for message in action.messages:
                    await self._dispatch(message)
                if action.close_connection:
                    break
        finally:
            self._client_writers.discard(writer)
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, message: PushMessage) -> None:
        """Deliver one message to every registered callback."""
        loop = asyncio.get_running_loop()
        for callback in list(self._callbacks):
            try:
                result = callback(message)
                if asyncio.iscoroutine(result):
                    await result  # type: ignore[func-returns-value]
            except Exception as exc:
                loop.call_exception_handler(
                    {
                        "message": "Unhandled DMP push listener callback exception",
                        "exception": exc,
                        "callback": callback,
                        "push_message": message,
                        "listener": self,
                    }
                )
