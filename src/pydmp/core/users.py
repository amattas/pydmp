"""Stateless `?P=` user-table transaction and reply parsing."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from .errors import SessionProtocolError
from .models import (
    PanelEndpoint,
    Transaction,
    TransactionRunner,
    ack_or_deny,
    payload_required,
)

USER_RECORD_SEPARATOR: Final[bytes] = b"\x1e"
USER_REPLY_PREFIXES: Final[tuple[bytes, ...]] = (b"*P=", b"!P=", b"?P=")
USER_START_SELECTOR: Final[str] = "0000"
USER_MAX_SELECTOR: Final[int] = 9999
USER_MAX_PAGES: Final[int] = 200
USER_MAX_ROWS_PER_PAGE: Final[int] = 2
USER_PAGE_TERMINATOR: Final[bytes] = b"----"
USER_LFSR_CONTROL_STRING: Final[str] = "----2222222223333"
USER_WRITE_REPLY_PREFIXES: Final[tuple[bytes, ...]] = (b"+P", b"-P")
USER_WRITE_POST_NAME_SUFFIX: Final[str] = "----00000"
EXPERIMENTAL_WRITE_USER_MESSAGE: Final[str] = (
    "TransactionWriteUser is experimental and intentionally disabled on the main core surface. "
    "Pass allow_experimental_write_user=True only on dedicated experimental work."
)


@dataclass(slots=True)
class UserFlags:
    """Three parsed user-flag bits from the user tail."""

    active: bool
    authority_1: bool
    temporary: bool


@dataclass(slots=True)
class UserRecord:
    """One parsed user record from a `?P=` reply."""

    number: str
    code: str
    pin: str
    profiles: tuple[str | None, str | None, str | None, str | None]
    end_date: str | None
    legacy_exp: str | None
    flags: UserFlags | None
    start_date: str | None
    name: str


@dataclass(slots=True)
class UserPage:
    """One parsed `?P=` reply page."""

    users: list[UserRecord]
    complete: bool
    raw_reply: bytes


@dataclass(slots=True)
class UserReply:
    """Parsed result of a complete `?P=` user-table transaction."""

    users: list[UserRecord]
    complete: bool
    raw_replies: list[bytes]


@dataclass(slots=True)
class UserWriteReply:
    """Parsed reply for one `!P=` write when the panel sends one."""

    acknowledged: bool
    detail: str | None


class TransactionQueryUsers(Transaction):
    """Complete paged `?P=` user-table query using seeded highest-user continuation."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(
            body=f"?P={USER_START_SELECTOR}",
            completion=payload_required(),
            label="query_users",
        )

    async def execute_in_session(
        self,
        exchange: TransactionRunner,
        *,
        session_mode,
        endpoint: PanelEndpoint | None = None,
    ) -> Transaction:
        if endpoint is None:
            raise SessionProtocolError("User query requires endpoint context")

        account_number = int(endpoint.account, 10)
        remote_key = endpoint.remote_key or ""
        selector = USER_START_SELECTOR
        users: list[UserRecord] = []
        raw_replies: list[bytes] = []
        pages = 0
        seen_start_selectors: set[str] = set()

        while pages < USER_MAX_PAGES:
            pages += 1
            if selector in seen_start_selectors:
                raise SessionProtocolError(f"User query selector walk repeated at {selector!r}")
            seen_start_selectors.add(selector)

            exchange_result = await exchange(f"?P={selector}", self.completion)
            self.record_exchange(exchange_result, session_mode=session_mode)

            if exchange_result.response is None:
                raise SessionProtocolError("User query completed without a reply payload")

            page = parse_user_page(
                exchange_result.response,
                account_number=account_number,
                remote_key=remote_key,
            )
            raw_replies.append(page.raw_reply)
            users.extend(page.users)

            next_selector = _next_user_selector(page.users)
            if next_selector is None:
                self.parsed_response = UserReply(
                    users=users,
                    complete=True,
                    raw_replies=raw_replies,
                )
                return self

            if int(next_selector, 10) <= int(selector, 10):
                raise SessionProtocolError(
                    f"User query selector walk did not advance: {selector!r} -> {next_selector!r}"
                )
            selector = next_selector

        raise SessionProtocolError("User query exceeded max page count")


class TransactionWriteUser(Transaction):
    """Write one local-integrator style `!P=` user record.

    This transaction is intentionally kept experimental until live-write
    behavior is better proven across panels and edge cases.

    This transaction intentionally uses the safest current local write shape:
    - fixed local record layout
    - mandatory trailing `0x1e` record separator after the name
    - mandatory post-separator `----xxxxx` suffix
    """

    __slots__ = (
        "user_number",
        "delete",
        "code",
        "pin",
        "profile_slots",
        "end_date",
        "field_40_43",
        "active",
        "flag_2",
        "temporary",
        "start_date",
        "name",
        "plain_record",
        "wire_record",
    )

    def __init__(
        self,
        user_number: int | str,
        *,
        allow_experimental_write_user: bool = False,
        code: str = "",
        name: str,
        profiles: Iterable[int | str],
        pin: str = "",
        delete: bool = False,
        active: bool = True,
        flag_2: bool = False,
        temporary: bool = False,
        start_date: str = "000000",
        end_date: str = "000000",
        field_40_43: str = "----",
    ) -> None:
        if not allow_experimental_write_user:
            raise RuntimeError(EXPERIMENTAL_WRITE_USER_MESSAGE)
        super().__init__(
            body="!P=",
            completion=ack_or_deny(),
            label="write_user",
            parser=parse_user_write_reply,
        )
        self.user_number = normalize_user_number(user_number, allow_zero=False)
        self.delete = bool(delete)
        if self.delete:
            self.code = "F" * 12
            self.pin = "F" * 6
        else:
            self.code = _normalize_user_code(code)
            self.pin = _normalize_user_pin(pin)
        self.profile_slots = _normalize_user_profiles(profiles)
        self.end_date = _normalize_user_date(end_date, field_name="end_date")
        self.field_40_43 = _normalize_user_field_40_43(field_40_43)
        self.active = bool(active)
        self.flag_2 = bool(flag_2)
        self.temporary = bool(temporary)
        self.start_date = _normalize_user_date(start_date, field_name="start_date")
        self.name = _normalize_user_name(name)
        self.plain_record = _build_plain_user_record(
            user_number=self.user_number,
            code=self.code,
            pin=self.pin,
            profile_slots=self.profile_slots,
            end_date=self.end_date,
            field_40_43=self.field_40_43,
            active=self.active,
            flag_2=self.flag_2,
            temporary=self.temporary,
            start_date=self.start_date,
            name=self.name,
        )
        self.wire_record: str | None = None

    async def execute_in_session(
        self,
        exchange: TransactionRunner,
        *,
        session_mode,
        endpoint: PanelEndpoint | None = None,
    ) -> Transaction:
        if endpoint is None:
            raise SessionProtocolError("User write requires endpoint context")

        account_number = int(endpoint.account, 10)
        remote_key = endpoint.remote_key or ""
        self.wire_record = _transform_user_record(
            self.plain_record,
            account_number=account_number,
            remote_key=remote_key,
        )
        # Local writes only completed cleanly once the post-name suffix was restored.
        self.body = (
            f"!P={self.wire_record}"
            f"{USER_RECORD_SEPARATOR.decode('ascii')}"
            f"{USER_WRITE_POST_NAME_SUFFIX}"
        )

        exchange_result = await exchange(self.body, self.completion)
        self.record_exchange(exchange_result, session_mode=session_mode)
        return self


def parse_user_page(
    reply: bytes,
    *,
    account_number: int,
    remote_key: str = "",
) -> UserPage:
    """Parse one raw panel reply page for the `?P=` family."""
    payload = _extract_user_payload(reply)
    cleaned = payload.rstrip(b"\r\x00")
    if cleaned == USER_PAGE_TERMINATOR:
        return UserPage(users=[], complete=True, raw_reply=reply)
    if not cleaned:
        raise SessionProtocolError("Empty ?P= reply payload")

    parts = cleaned.split(USER_RECORD_SEPARATOR)
    users: list[UserRecord] = []
    complete = False

    for part in parts:
        if not part:
            raise SessionProtocolError(f"Malformed ?P= reply contained an empty record: {reply!r}")
        if complete:
            raise SessionProtocolError(f"Malformed ?P= reply contained data after terminator: {reply!r}")
        if part == USER_PAGE_TERMINATOR:
            complete = True
            continue

        try:
            raw_record = part.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise SessionProtocolError(f"Malformed ?P= user record: {reply!r}") from exc
        users.append(_decode_user_record(raw_record, account_number=account_number, remote_key=remote_key))
        if len(users) > USER_MAX_ROWS_PER_PAGE:
            raise SessionProtocolError(
                f"Malformed ?P= reply exceeded {USER_MAX_ROWS_PER_PAGE} rows: {reply!r}"
            )

    if not complete:
        raise SessionProtocolError(f"Malformed ?P= reply missing terminator: {reply!r}")

    return UserPage(users=users, complete=complete, raw_reply=reply)


def parse_user_write_reply(reply: bytes) -> UserWriteReply:
    """Parse a visible `+P` or `-P` reply from a user write."""
    payload = _extract_write_reply_payload(reply).rstrip(b"\r\x00")
    if payload.startswith(b"+P"):
        detail = payload[2:].decode("ascii", errors="strict") or None
        return UserWriteReply(acknowledged=True, detail=detail)
    if payload.startswith(b"-P"):
        detail = payload[2:].decode("ascii", errors="strict") or None
        return UserWriteReply(acknowledged=False, detail=detail)
    raise SessionProtocolError("Reply did not contain a recognized P write marker")


def _extract_user_payload(reply: bytes) -> bytes:
    """Extract the body that follows the `*P=`/`!P=`/`?P=` marker."""
    for marker in USER_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index + len(marker):]

    raise SessionProtocolError("Reply did not contain a P= marker")


def _extract_write_reply_payload(reply: bytes) -> bytes:
    """Return the `+P...` or `-P...` portion of one reply."""
    for marker in USER_WRITE_REPLY_PREFIXES:
        index = reply.find(marker)
        if index == -1:
            continue
        return reply[index:]
    raise SessionProtocolError("Reply did not contain a P write marker")


def _decode_user_record(
    raw_record: str,
    *,
    account_number: int,
    remote_key: str,
) -> UserRecord:
    """Decrypt and parse one user record from a `?P=` page."""
    plain = _decrypt_user_record(raw_record, account_number=account_number, remote_key=remote_key)
    if len(plain) < 44:
        raise SessionProtocolError("Decrypted user record shorter than 44 chars")

    pin_raw = plain[16:22]
    profiles_raw = (plain[22:25], plain[25:28], plain[28:31], plain[31:34])
    tail = plain[44:]

    flags = None
    start_date = None
    name = ""
    if tail:
        maybe_flags = tail[0:3] if len(tail) >= 3 else ""
        maybe_start = tail[3:9] if len(tail) >= 9 else ""
        if (
            len(maybe_flags) == 3
            and all(char in "YN" for char in maybe_flags)
            and len(maybe_start) == 6
            and maybe_start.isdigit()
        ):
            flags = UserFlags(
                active=(maybe_flags[0] == "Y"),
                authority_1=(maybe_flags[1] == "Y"),
                temporary=(maybe_flags[2] == "Y"),
            )
            start_date = _maybe_empty_date(maybe_start)
            name = tail[9:]
        else:
            name = tail

    return UserRecord(
        number=plain[0:4],
        code=_strip_f_padding(plain[4:16]),
        pin=_strip_f_padding(pin_raw),
        profiles=tuple(_maybe_unused_profile(value) for value in profiles_raw),  # type: ignore[arg-type]
        end_date=_maybe_empty_date(plain[34:40]),
        legacy_exp=None if plain[40:44] == "----" else plain[40:44],
        flags=flags,
        start_date=start_date,
        name=name,
    )


def _next_user_selector(users: list[UserRecord]) -> str | None:
    """Return the next seeded selector using highest-visible-user progression."""
    if not users:
        return None
    user_numbers = [int(user.number, 10) for user in users if user.number.isdigit()]
    if not user_numbers:
        return None

    highest_user_number = max(user_numbers)
    if highest_user_number >= USER_MAX_SELECTOR:
        return None

    return f"{highest_user_number + 1:04d}"


def _decrypt_user_record(raw_record: str, *, account_number: int, remote_key: str) -> str:
    """Return the LFSR-deobfuscated cleartext for one user record."""
    return _transform_user_record(raw_record, account_number=account_number, remote_key=remote_key)


def _transform_user_record(value: str, *, account_number: int, remote_key: str) -> str:
    """Apply the symmetric user-record LFSR transform."""
    seed = _generate_user_seed(value[:4], account_number=account_number, remote_key=remote_key)
    result = list(value)
    string_pos = 0

    for control_char in USER_LFSR_CONTROL_STRING:
        if string_pos >= len(result):
            break

        if control_char == "3":
            if string_pos + 3 <= len(result):
                work_num = int("".join(result[string_pos:string_pos + 3]))
                seed = _advance_seed(seed)
                work_num = (work_num & 0xFF) ^ seed
                encrypted = f"{work_num:03d}"
                result[string_pos:string_pos + 3] = encrypted
                string_pos += 3
                continue

        if control_char == "2":
            if string_pos + 2 <= len(result):
                work_num = int("".join(result[string_pos:string_pos + 2]), 16)
                seed = _advance_seed(seed)
                work_num = work_num ^ seed
                encrypted = f"{work_num:02X}"
                result[string_pos:string_pos + 2] = encrypted
                string_pos += 2
                continue

        string_pos += 1

    return "".join(result)


def normalize_user_number(user_number: int | str, *, allow_zero: bool) -> str:
    """Normalize one user number to a 4-digit string."""
    normalized = str(user_number).strip()
    if not normalized.isdigit():
        raise ValueError(f"user_number must be numeric: {user_number!r}")
    number = int(normalized, 10)
    minimum = 0 if allow_zero else 1
    if not minimum <= number <= USER_MAX_SELECTOR:
        raise ValueError(f"user_number must be in {minimum:04d}..{USER_MAX_SELECTOR:04d}: {user_number!r}")
    return f"{number:04d}"


def _normalize_user_profiles(profiles: Iterable[int | str]) -> tuple[str, str, str, str]:
    """Normalize 1..4 profile numbers and pad unused slots with `255`."""
    normalized: list[str] = []
    for raw_profile in profiles:
        profile_text = str(raw_profile).strip()
        if not profile_text:
            continue
        if not profile_text.isdigit():
            raise ValueError(f"profile must be numeric: {raw_profile!r}")
        profile_number = int(profile_text, 10)
        if not 0 <= profile_number <= 255:
            raise ValueError(f"profile must be in 0..255: {raw_profile!r}")
        normalized.append(f"{profile_number:03d}")

    if not normalized:
        raise ValueError("at least one profile is required")
    if len(normalized) > 4:
        raise ValueError("at most 4 profiles may be supplied")

    while len(normalized) < 4:
        normalized.append("255")

    return (normalized[0], normalized[1], normalized[2], normalized[3])


def _normalize_user_code(code: str) -> str:
    """Normalize a required numeric user code to the 12-char field."""
    normalized = str(code).strip()
    if not normalized.isdigit():
        raise ValueError(f"code must be numeric: {code!r}")
    if not 1 <= len(normalized) <= 12:
        raise ValueError(f"code must be 1..12 digits: {code!r}")
    return normalized.ljust(12, "F")


def _normalize_user_pin(pin: str) -> str:
    """Normalize an optional numeric PIN to the 6-char field."""
    normalized = str(pin).strip()
    if not normalized:
        return "F" * 6
    if not normalized.isdigit():
        raise ValueError(f"pin must be numeric: {pin!r}")
    if not 1 <= len(normalized) <= 6:
        raise ValueError(f"pin must be 1..6 digits: {pin!r}")
    return normalized.ljust(6, "F")


def _normalize_user_date(value: str, *, field_name: str) -> str:
    """Normalize one 6-digit date field."""
    normalized = str(value).strip()
    if len(normalized) != 6 or not normalized.isdigit():
        raise ValueError(f"{field_name} must be exactly 6 digits in DDMMYY form: {value!r}")
    return normalized


def _normalize_user_field_40_43(value: str) -> str:
    """Normalize the currently-unknown 4-char user field."""
    normalized = str(value)
    if len(normalized) != 4:
        raise ValueError(f"field_40_43 must be exactly 4 characters: {value!r}")
    if "\r" in normalized or "\x1e" in normalized:
        raise ValueError("field_40_43 may not contain CR or 0x1e")
    return normalized


def _normalize_user_name(name: str) -> str:
    """Normalize the display name for one user record."""
    normalized = str(name)
    if not normalized:
        raise ValueError("name must not be empty")
    if "\r" in normalized or "\x1e" in normalized:
        raise ValueError("name may not contain CR or 0x1e")
    return normalized


def _build_plain_user_record(
    *,
    user_number: str,
    code: str,
    pin: str,
    profile_slots: tuple[str, str, str, str],
    end_date: str,
    field_40_43: str,
    active: bool,
    flag_2: bool,
    temporary: bool,
    start_date: str,
    name: str,
) -> str:
    """Build the cleartext user record before the LFSR transform."""
    flags = (
        ("Y" if active else "N")
        + ("Y" if flag_2 else "N")
        + ("Y" if temporary else "N")
    )
    return (
        f"{user_number}"
        f"{code}"
        f"{pin}"
        f"{''.join(profile_slots)}"
        f"{end_date}"
        f"{field_40_43}"
        f"{flags}"
        f"{start_date}"
        f"{name}"
    )


def _generate_user_seed(user_number: str, *, account_number: int, remote_key: str) -> int:
    """Return the initial 8-bit LFSR seed for one user record."""
    base_seed = (account_number + int(user_number[:4])) & 0xFF

    system_seed = 0
    if len(remote_key) >= 8:
        try:
            system_seed = int(remote_key[0:2], 16) ^ int(remote_key[6:8], 16)
        except ValueError:
            system_seed = 0

    return base_seed ^ system_seed
def _advance_seed(seed: int) -> int:
    """Advance one LFSR step and return the next seed value."""
    bit_val = (seed & 1) ^ ((seed >> 2) & 1) ^ ((seed >> 3) & 1) ^ ((seed >> 4) & 1)
    seed = seed >> 1
    if bit_val == 1:
        seed |= 0x80
    if seed == 0:
        seed = 255
    return seed


def _strip_f_padding(value: str) -> str:
    """Remove trailing `F` filler from one field."""
    return value.split("F", 1)[0]


def _maybe_empty_date(value: str) -> str | None:
    """Return `None` for empty/sentinel date fields."""
    if not value:
        return None
    if value in {"000000", "------"}:
        return None
    return value


def _maybe_unused_profile(value: str) -> str | None:
    """Return `None` for unused profile slots."""
    if value == "255" or not value:
        return None
    return value
