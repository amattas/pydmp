"""Small compatibility helpers shared by the wrapper package.

The wrapper layer has one job: let existing `pydmp`-style application code
talk to the new core without forcing a full rewrite on day one.

To keep the actual wrapper classes readable, this file holds the boring
translation pieces:

- old public exceptions mapped from new-core failures
- old state strings mapped from new-core records
- old `UserCode` / `UserProfile` dataclasses built from new-core records
"""

from __future__ import annotations

from ..const.events import DMPRealTimeStatusEvent
from ..const.responses import AREA_STATUS_ARMED_AWAY, AREA_STATUS_DISARMED
from ..core.errors import (
    CommandSessionError,
    SessionClosedError,
    SessionConnectError,
    SessionHandshakeError,
    SessionProtocolError,
    SessionTimeoutError,
    TransactionParseError,
)
from ..exceptions import (
    DMPConnectionError,
    DMPError,
    DMPInvalidResponseError,
    DMPProtocolError,
)
from ..profile import UserProfile
from ..user import UserCode

# The old panel API felt like a long-lived connection. The wrapper keeps that
# behavior by asking the new manager to hold sessions open until explicit
# disconnect, unless the caller chooses otherwise later.
WRAPPER_IDLE_DISCONNECT_SECONDS = 24 * 60 * 60.0


def map_core_error(error: Exception, *, context: str) -> DMPError:
    """Translate a new-core exception into the closest old public error type."""
    message = f"{context}: {error}"

    if isinstance(error, (SessionConnectError, SessionHandshakeError, SessionTimeoutError, SessionClosedError)):
        return DMPConnectionError(message)
    if isinstance(error, (SessionProtocolError, TransactionParseError)):
        return DMPInvalidResponseError(message)
    if isinstance(error, CommandSessionError):
        return DMPProtocolError(message)
    return DMPError(message)


def map_area_state(state: str) -> str:
    """Convert the new-core `?WA` state character into the old area-state vocabulary."""
    if state == "N":
        return AREA_STATUS_DISARMED
    if state in {"Y", "B"}:
        return AREA_STATUS_ARMED_AWAY
    return state


def map_output_state(status: str) -> str:
    """Convert one visible `?WQ` mode/status byte into the old output-state text."""
    mapping = {
        "O": DMPRealTimeStatusEvent.OUTPUT_OFF.value,
        "P": DMPRealTimeStatusEvent.OUTPUT_PULSE.value,
        "S": DMPRealTimeStatusEvent.OUTPUT_ON.value,
        "T": DMPRealTimeStatusEvent.OUTPUT_TEMPORAL.value,
        "M": DMPRealTimeStatusEvent.OUTPUT_MOMENTARY.value,
        "W": DMPRealTimeStatusEvent.OUTPUT_MOMENTARY.value,
        "A": DMPRealTimeStatusEvent.OUTPUT_MOMENTARY.value,
        "a": DMPRealTimeStatusEvent.OUTPUT_MOMENTARY.value,
        "t": DMPRealTimeStatusEvent.OUTPUT_MOMENTARY.value,
        # Some callers may feed already-expanded states back through here.
        DMPRealTimeStatusEvent.OUTPUT_OFF.value: DMPRealTimeStatusEvent.OUTPUT_OFF.value,
        DMPRealTimeStatusEvent.OUTPUT_PULSE.value: DMPRealTimeStatusEvent.OUTPUT_PULSE.value,
        DMPRealTimeStatusEvent.OUTPUT_ON.value: DMPRealTimeStatusEvent.OUTPUT_ON.value,
        DMPRealTimeStatusEvent.OUTPUT_TEMPORAL.value: DMPRealTimeStatusEvent.OUTPUT_TEMPORAL.value,
        DMPRealTimeStatusEvent.OUTPUT_MOMENTARY.value: DMPRealTimeStatusEvent.OUTPUT_MOMENTARY.value,
    }
    return mapping.get(status, status)


def build_user_code(record) -> UserCode:
    """Build the old `UserCode` dataclass from one new-core user record."""
    flags_text = None
    active = None
    temporary = None

    if record.flags is not None:
        active = bool(record.flags.active)
        temporary = bool(record.flags.temporary)
        flags_text = "".join("Y" if value else "N" for value in (record.flags.active, record.flags.authority_1, record.flags.temporary))

    return UserCode(
        number=record.number,
        code=record.code,
        pin=record.pin,
        profiles=tuple(profile or "" for profile in record.profiles),
        temp_date=record.end_date or "",
        exp_date=record.legacy_exp or "",
        name=record.name,
        start_date=record.start_date,
        end_date=record.end_date,
        flags=flags_text,
        active=active,
        temporary=temporary,
    )


def build_user_profile(record) -> UserProfile:
    """Build the old `UserProfile` dataclass from one new-core profile record."""
    return UserProfile(
        number=record.number,
        areas_mask=record.areas_mask,
        access_areas_mask=record.access_areas_mask,
        output_group=record.output_group,
        menu_options=record.menu_options,
        rearm_delay=record.rearm_delay or "",
        name=record.name,
    )


def status_message_definition(message: object) -> str | None:
    """Return the pushed event family from either old or new listener messages."""
    definition = getattr(message, "definition", None)
    if isinstance(definition, str):
        return definition

    event = getattr(message, "event", None)
    definition = getattr(event, "definition", None)
    if isinstance(definition, str):
        return definition

    return None
