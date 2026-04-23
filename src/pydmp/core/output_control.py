"""Stateless `!Q` output-control transaction and reply parsing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import SessionProtocolError
from .models import Transaction, ack_or_deny
from .output_status import normalize_output_selector


class OutputControlMode(str, Enum):
    """Known `!Q` mode bytes from the XR150 213 firmware table."""

    OFF = "O"
    PULSE = "P"
    STEADY = "S"
    MOMENTARY = "M"
    RAW_T = "T"
    RAW_W = "W"
    LOWER_A = "a"
    LOWER_T = "t"


OUTPUT_CONTROL_MODE_BYTES = frozenset(mode.value for mode in OutputControlMode)
OUTPUT_CONTROL_MODE_ALIASES = {
    "off": OutputControlMode.OFF.value,
    "o": OutputControlMode.OFF.value,
    "pulse": OutputControlMode.PULSE.value,
    "p": OutputControlMode.PULSE.value,
    "on": OutputControlMode.STEADY.value,
    "steady": OutputControlMode.STEADY.value,
    "s": OutputControlMode.STEADY.value,
    "momentary": OutputControlMode.MOMENTARY.value,
    "m": OutputControlMode.MOMENTARY.value,
    "w": OutputControlMode.RAW_W.value,
}


@dataclass(slots=True)
class OutputControlReply:
    """Parsed reply for a `!Q` command."""

    selector: str | None
    mode: str | None
    acknowledged: bool
    detail: str | None


class TransactionSetOutput(Transaction):
    """Set one `?WQ` selector with the firmware-backed `!Q` command.

    Practical safety guidance:
    - poll outputs first with `?WQ`
    - limit writes to selectors known to be valid on the current panel

    The parser accepts the full firmware-backed visible selector grammar, but
    that is broader than the set of selectors proven populated on any one
    system.
    """

    __slots__ = ("mode", "selector")

    def __init__(self, selector: int | str, mode: str | OutputControlMode) -> None:
        normalized_selector = normalize_output_selector(selector)
        normalized_mode = normalize_output_control_mode(mode)
        self.selector = normalized_selector
        self.mode = normalized_mode
        super().__init__(
            body=f"!Q{normalized_selector}{normalized_mode}",
            completion=ack_or_deny(),
            label="set_output",
            parser=lambda reply: parse_output_control_reply(
                reply,
                selector=normalized_selector,
                mode=normalized_mode,
            ),
        )


def normalize_output_control_mode(mode: str | OutputControlMode) -> str:
    """Return one firmware-valid `!Q` mode byte.

    The 213 firmware lookup table accepts only `O`, `P`, `S`, `M`, `T`, `W`,
    `a`, and `t`. Unknown bytes are dangerous because the parser can still
    report success after passing an out-of-table index deeper into the output
    state machinery.

    Selector `0` is intentionally not exposed here. Firmware has a special
    selector-zero path for `!Q...O`, but the safe public surface is the normal
    visible selector space handled by `normalize_output_selector()`.
    """

    if isinstance(mode, OutputControlMode):
        return mode.value

    text = str(mode).strip()
    if not text:
        raise ValueError("Output control mode must not be empty")

    if text in OUTPUT_CONTROL_MODE_BYTES:
        return text

    alias = OUTPUT_CONTROL_MODE_ALIASES.get(text.lower())
    if alias is not None:
        return alias

    raise ValueError(
        "Output control mode must be one of O, P, S, M, T, W, a, or t"
    )


def parse_output_control_reply(
    reply: bytes,
    *,
    selector: str | None = None,
    mode: str | None = None,
) -> OutputControlReply:
    """Parse one local panel reply for `!Q`.

    Firmware success emits status `+Q`. The same router branch can deny as
    `-Q`, privilege-fail as `-VV`, or compatibility-fail as `-QV`.
    """

    positive_markers = (b"+!Q", b"+Q")
    negative_markers = (b"-!Q", b"-QV", b"-Q", b"-VV")

    positive = _find_first_marker(reply, positive_markers)
    negative = _find_first_marker(reply, negative_markers)

    if positive is not None and (negative is None or positive[0] < negative[0]):
        index, marker = positive
        detail = _extract_detail(reply[index + len(marker) :])
        return OutputControlReply(
            selector=selector,
            mode=mode,
            acknowledged=True,
            detail=detail,
        )

    if negative is not None:
        index, marker = negative
        if marker == b"-VV":
            detail = "VV"
        elif marker == b"-QV":
            detail = "QV"
        else:
            detail = _extract_detail(reply[index + len(marker) :])
        return OutputControlReply(
            selector=selector,
            mode=mode,
            acknowledged=False,
            detail=detail,
        )

    raise SessionProtocolError("Reply did not contain a Q command marker")


def _find_first_marker(reply: bytes, markers: tuple[bytes, ...]) -> tuple[int, bytes] | None:
    """Return the earliest matching marker in a reply."""

    matches = [(index, marker) for marker in markers if (index := reply.find(marker)) != -1]
    if not matches:
        return None
    return min(matches, key=lambda item: item[0])


def _extract_detail(suffix: bytes) -> str | None:
    """Return any reply detail that follows a `!Q` status marker."""

    cleaned = suffix.replace(b"\x00", b"").replace(b"\r", b"").replace(b"\n", b"")
    if cleaned.startswith(b"\x1e"):
        cleaned = cleaned[1:]
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    return cleaned.decode("ascii", errors="replace")
