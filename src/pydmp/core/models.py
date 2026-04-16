"""Small data models used by the stateless core."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum

from .secure_s import normalize_secure_s_passphrase_slot
from .wrapped_v3 import (
    build_v30_code_field12,
    normalize_panel_serial,
    normalize_v30_tail4,
    normalize_v31_material,
)


class SessionMode(str, Enum):
    """Supported command-session modes."""

    BLANK_V2 = "blank_v2"
    KEYED_V2 = "keyed_v2"
    V31 = "v31"
    V30 = "v30"
    SECURE_S = "secure_s"


class ReplyExpectation(str, Enum):
    """How much reply data a transaction needs to complete."""

    PAYLOAD_REQUIRED = "payload_required"
    ACK_OR_DENY = "ack_or_deny"
    REPLY_OPTIONAL = "reply_optional"
    NO_REPLY_EXPECTED = "no_reply_expected"


@dataclass(slots=True)
class CompletionPolicy:
    """Reply and timeout rules for one transaction."""

    reply_expectation: ReplyExpectation
    first_reply_timeout: float = 1.0
    inter_frame_timeout: float = 0.25
    overall_timeout: float | None = None


TransactionParser = Callable[[bytes], object]
TransactionRunner = Callable[[bytes | str, CompletionPolicy], Awaitable["TransactionExchangeResult"]]


@dataclass(slots=True)
class TransactionExchangeResult:
    """One wire exchange inside a larger transaction."""

    wire_request: bytes
    response: bytes | None
    wire_response: bytes | None = None


@dataclass(slots=True)
class Transaction:
    """One logical command/query exchange."""

    body: bytes | str
    completion: CompletionPolicy
    label: str | None = None
    parser: TransactionParser | None = None
    response: bytes | None = None
    parsed_response: object | None = None
    had_reply: bool = False
    wire_request: bytes | None = None
    wire_response: bytes | None = None
    responses: list[bytes] = field(default_factory=list)
    wire_requests: list[bytes] = field(default_factory=list)
    wire_responses: list[bytes] = field(default_factory=list)
    session_mode: SessionMode | None = None

    def apply_parser(self) -> object | None:
        """Parse the reply if this transaction carries a parser."""
        if self.parsed_response is not None:
            return self.parsed_response

        if self.parser is None or self.response is None:
            return None

        parsed = self.parser(self.response)
        self.parsed_response = parsed
        return parsed

    def record_exchange(
        self,
        exchange_result: TransactionExchangeResult,
        *,
        session_mode: SessionMode,
    ) -> None:
        """Record one wire exchange inside this transaction."""
        self.session_mode = session_mode
        self.wire_request = exchange_result.wire_request
        self.wire_response = exchange_result.wire_response
        self.response = exchange_result.response
        self.wire_requests.append(exchange_result.wire_request)

        if exchange_result.wire_response is not None:
            self.wire_responses.append(exchange_result.wire_response)

        if exchange_result.response is not None:
            self.responses.append(exchange_result.response)
            self.had_reply = True

    async def execute_in_session(
        self,
        exchange: TransactionRunner,
        *,
        session_mode: SessionMode,
        endpoint: "PanelEndpoint | None" = None,
    ) -> Transaction:
        """Execute this transaction inside an open session.

        The default implementation is a single request/reply exchange.
        Transaction subclasses can override this when one logical transaction
        needs multiple wire exchanges.
        """
        del endpoint
        exchange_result = await exchange(self.body, self.completion)
        self.record_exchange(exchange_result, session_mode=session_mode)
        return self


@dataclass(slots=True)
class PanelEndpoint:
    """Addressing and connection policy for one panel."""

    host: str
    account: str
    port: int = 8011
    remote_key: str | None = None
    v31_compare_material: str | None = None
    panel_serial: str | None = None
    user_code: str | None = None
    passphrase: str | None = None
    v30_tail4: str | None = None
    connect_timeout: float = 10.0
    idle_disconnect_seconds: float = 4.0
    rate_limit_seconds: float = 0.25

    def __post_init__(self) -> None:
        """Apply light validation to the public endpoint inputs."""
        self.host = _normalize_host(self.host)
        self.account = _normalize_account(self.account)
        self.port = _normalize_port(self.port)
        self.connect_timeout = _normalize_positive_timeout(
            self.connect_timeout,
            label="connect_timeout",
        )
        self.idle_disconnect_seconds = _normalize_non_negative_timeout(
            self.idle_disconnect_seconds,
            label="idle_disconnect_seconds",
        )
        self.rate_limit_seconds = _normalize_non_negative_timeout(
            self.rate_limit_seconds,
            label="rate_limit_seconds",
        )

        if self.remote_key is not None:
            self.remote_key = _normalize_remote_key(self.remote_key)
        if self.v31_compare_material is not None:
            self.v31_compare_material = normalize_v31_material(self.v31_compare_material)
        if self.panel_serial is not None:
            self.panel_serial = normalize_panel_serial(self.panel_serial)
        if self.user_code is not None:
            self.user_code = build_v30_code_field12(self.user_code).decode("ascii").strip()
        if self.passphrase is not None:
            normalize_secure_s_passphrase_slot(self.passphrase)
        if self.v30_tail4 is not None:
            self.v30_tail4 = normalize_v30_tail4(self.v30_tail4).decode("ascii")

    @property
    def normalized_account(self) -> str:
        """Return the panel account left-padded to 5 characters."""
        return str(self.account).strip().rjust(5)


@dataclass(slots=True)
class SessionState:
    """Mutable state for one active command session."""

    mode: SessionMode
    metadata: dict[str, object] = field(default_factory=dict)


def payload_required() -> CompletionPolicy:
    """Default policy for query transactions."""
    return CompletionPolicy(reply_expectation=ReplyExpectation.PAYLOAD_REQUIRED)


def ack_or_deny() -> CompletionPolicy:
    """Default policy for command acknowledgements."""
    return CompletionPolicy(reply_expectation=ReplyExpectation.ACK_OR_DENY)


def reply_optional() -> CompletionPolicy:
    """Default policy when a reply may or may not arrive."""
    return CompletionPolicy(reply_expectation=ReplyExpectation.REPLY_OPTIONAL)


def no_reply_expected() -> CompletionPolicy:
    """Default policy for fire-and-forget traffic."""
    return CompletionPolicy(reply_expectation=ReplyExpectation.NO_REPLY_EXPECTED)


def _normalize_host(host: str) -> str:
    """Return a non-empty host string."""
    normalized = str(host).strip()
    if not normalized:
        raise ValueError("Host must not be empty")
    return normalized


def _normalize_account(account: str) -> str:
    """Return a 1..5 digit account string."""
    normalized = str(account).strip()
    if not normalized.isdigit():
        raise ValueError(f"Account must be 1..5 digits: {account!r}")
    if not 1 <= len(normalized) <= 5:
        raise ValueError(f"Account must be 1..5 digits: {account!r}")
    return normalized


def _normalize_port(port: int) -> int:
    """Return a valid TCP port number."""
    value = int(port)
    if not 1 <= value <= 65535:
        raise ValueError(f"Port must be in 1..65535: {port!r}")
    return value


def _normalize_remote_key(remote_key: str) -> str:
    """Return a 16-byte ASCII remote key."""
    normalized = str(remote_key)
    try:
        normalized.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Remote key must be ASCII") from exc
    if len(normalized) != 16:
        raise ValueError(f"Remote key must be exactly 16 ASCII characters: {remote_key!r}")
    return normalized


def _normalize_positive_timeout(value: float, *, label: str) -> float:
    """Return a timeout that must be greater than zero."""
    normalized = float(value)
    if normalized <= 0:
        raise ValueError(f"{label} must be greater than 0: {value!r}")
    return normalized


def _normalize_non_negative_timeout(value: float, *, label: str) -> float:
    """Return a timeout/delay that must not be negative."""
    normalized = float(value)
    if normalized < 0:
        raise ValueError(f"{label} must be >= 0: {value!r}")
    return normalized
