"""Session profiles for the stateless core.

Each profile answers the same practical question:
"How do we open a session, send commands through it, and close it cleanly?"

Keeping that logic here lets the manager stay small. The manager only has to
decide when work should run. The session profile decides what the wire traffic
looks like for blank `!V2`, keyed `!V2`, wrapped `V30`/`V31`, and secure `!!S`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .errors import (
    SessionHandshakeError,
    SessionProtocolError,
)
from .framing import (
    BLANK_V2_COMPARE,
    extract_v_denials,
    format_account_frame,
    is_v_banner_success,
)
from .models import (
    PanelEndpoint,
    SessionMode,
    SessionState,
    Transaction,
    TransactionExchangeResult,
    payload_required,
    reply_optional,
)
from .secure_s import (
    SECURE_S_FRAME_TYPE_DATA,
    SECURE_S_FRAME_TYPE_SETUP_REPLY,
    SECURE_S_PREFIX,
    build_secure_s_frame,
    build_secure_s_setup_frame,
    expected_secure_s_setup_reply_ack,
    next_secure_s_send_sequence,
    parse_secure_s_frame,
)
from .transport import TransportProtocol
from .wrapped_v3 import (
    V3_TRAILER_SPACE,
    build_v30_auth_body,
    build_v31_auth_body,
    encode_account_v3_frame,
    normalize_plain_reply,
    normalize_wrapped_reply,
)


class SessionProfile(Protocol):
    """Common shape for all session profiles.

    A profile owns the handshake rules for one lane. Once the profile has
    opened a session, every transaction uses the same `execute()` hook.
    """

    mode: SessionMode

    async def open(self, endpoint: PanelEndpoint, transport: TransportProtocol) -> SessionState:
        """Open one session on an already-connected transport."""

    async def close(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
    ) -> None:
        """Close one session cleanly."""

    async def execute(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
        transaction: Transaction,
    ) -> Transaction:
        """Execute one transaction inside the active session."""


# Project captures only show `-VB` continuing into a healthy session. Every
# other `-V*` denial is treated as fatal so we do not continue in a half-open
# state that may fail later in less obvious ways.
_BLANK_V2_SOFT_DENIALS = (b"-VB",)


@dataclass(slots=True)
class SessionProfileBlankV2:
    """Blank local `!V2` profile for the common clear Integrator lane."""

    mode: SessionMode = SessionMode.BLANK_V2

    async def open(self, endpoint: PanelEndpoint, transport: TransportProtocol) -> SessionState:
        """Open a blank `!V2` session.

        This is the simplest lane in the project notes, so it is also the
        default profile used by `CorePanelClient`.
        """
        request = format_account_frame(endpoint.normalized_account, b"!V2" + BLANK_V2_COMPARE)
        reply = await transport.exchange(request, payload_required())

        # Some panels send a denial code and still allow the session to
        # continue. We only allow the one soft denial that captures have shown
        # to be safe.
        denials = extract_v_denials(reply)
        fatal = next((d for d in denials if d not in _BLANK_V2_SOFT_DENIALS), None)
        if fatal is not None:
            raise SessionHandshakeError(
                f"Blank V2 authentication denied by panel ({fatal.decode('ascii')})"
            )

        soft_denial = denials[0] if denials else None
        if soft_denial is None and not is_v_banner_success(reply):
            raise SessionHandshakeError("Blank V2 authentication reply was not recognized")

        return SessionState(mode=self.mode, metadata={"auth_reply": reply, "auth_denial_code": soft_denial})

    async def close(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
    ) -> None:
        """Ask the panel to close the local session before the socket closes."""
        del state
        request = format_account_frame(endpoint.normalized_account, "!V0")
        try:
            await transport.exchange(request, reply_optional())
        except Exception:
            # Session shutdown should not hide the original caller intent.
            return

    async def execute(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
        transaction: Transaction,
    ) -> Transaction:
        """Execute one transaction inside the blank local V2 session."""
        del state

        async def exchange(body: bytes | str, completion) -> TransactionExchangeResult:
            request = format_account_frame(endpoint.normalized_account, body)
            reply = await transport.exchange(request, completion)
            return TransactionExchangeResult(wire_request=request, response=reply or None, wire_response=reply or None)

        return await transaction.execute_in_session(exchange, session_mode=self.mode, endpoint=endpoint)


def _normalize_v3_reply(raw_reply: bytes) -> bytes:
    """Return the clear parser-facing payload for a wrapped local V3 reply.

    Most transaction parsers should not care whether the session was wrapped.
    They should see the same clear reply body they would have received on a
    non-wrapped lane.
    """
    try:
        normalized, _wrapped = normalize_wrapped_reply(raw_reply)
        return normalized
    except ValueError:
        try:
            return normalize_plain_reply(raw_reply)
        except ValueError as exc:
            raise SessionProtocolError(str(exc)) from exc


async def _close_wrapped_v3_session(
    endpoint: PanelEndpoint,
    transport: TransportProtocol,
) -> None:
    """Close a wrapped local V3 session with a wrapped `!V0` request."""
    request = encode_account_v3_frame(endpoint.normalized_account, "!V0", V3_TRAILER_SPACE)
    try:
        await transport.exchange(request, reply_optional())
    except Exception:
        return


async def _execute_wrapped_v3_transaction(
    endpoint: PanelEndpoint,
    transport: TransportProtocol,
    session_mode: SessionMode,
    transaction: Transaction,
) -> Transaction:
    """Execute one logical transaction inside a wrapped local V3 session."""

    async def exchange(body: bytes | str, completion) -> TransactionExchangeResult:
        request = encode_account_v3_frame(endpoint.normalized_account, body, V3_TRAILER_SPACE)
        raw_reply = await transport.exchange(request, completion)
        response = None if not raw_reply else _normalize_v3_reply(raw_reply)
        return TransactionExchangeResult(wire_request=request, response=response, wire_response=raw_reply or None)

    return await transaction.execute_in_session(exchange, session_mode=session_mode, endpoint=endpoint)


# Captures show keyed and blank `!V2` share the same soft-denial behavior, so
# we keep the same allowlist here.
_KEYED_V2_SOFT_DENIALS = (b"-VB",)


@dataclass(slots=True)
class SessionProfileKeyedV2:
    """Keyed `!V2` session profile.

    Use this when the panel expects `!V2<remote_key>` instead of the blank
    compare block.
    """

    remote_key: str
    mode: SessionMode = SessionMode.KEYED_V2

    async def open(self, endpoint: PanelEndpoint, transport: TransportProtocol) -> SessionState:
        """Open a keyed `!V2` session using the configured remote key."""
        remote_key = self.remote_key or endpoint.remote_key
        if not remote_key:
            raise SessionHandshakeError("Keyed V2 requires a remote key")

        request = format_account_frame(endpoint.normalized_account, f"!V2{remote_key}")
        reply = await transport.exchange(request, payload_required())

        denials = extract_v_denials(reply)
        fatal = next((d for d in denials if d not in _KEYED_V2_SOFT_DENIALS), None)
        if fatal is not None:
            raise SessionHandshakeError(
                f"Keyed V2 authentication denied by panel ({fatal.decode('ascii')})"
            )

        soft_denial = denials[0] if denials else None
        if soft_denial is None and not is_v_banner_success(reply):
            raise SessionHandshakeError("Keyed V2 authentication reply was not recognized")

        return SessionState(mode=self.mode, metadata={"auth_reply": reply, "auth_denial_code": soft_denial, "remote_key": remote_key})

    async def close(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
    ) -> None:
        """Send `!V0` and ignore close-time transport problems."""
        del state
        request = format_account_frame(endpoint.normalized_account, "!V0")
        try:
            await transport.exchange(request, reply_optional())
        except Exception:
            return

    async def execute(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
        transaction: Transaction,
    ) -> Transaction:
        """Execute one transaction inside the keyed local V2 session."""
        del state

        async def exchange(body: bytes | str, completion) -> TransactionExchangeResult:
            request = format_account_frame(endpoint.normalized_account, body)
            reply = await transport.exchange(request, completion)
            return TransactionExchangeResult(wire_request=request, response=reply or None, wire_response=reply or None)

        return await transaction.execute_in_session(exchange, session_mode=self.mode, endpoint=endpoint)


@dataclass(slots=True)
class SessionProfileV31:
    """Wrapped local `V31` session profile.

    `V31` is the compare-material variant of the wrapped local session.
    Successful authentication switches the lane into wrapped traffic.
    """

    compare_material: str | None = None
    mode: SessionMode = SessionMode.V31

    async def open(self, endpoint: PanelEndpoint, transport: TransportProtocol) -> SessionState:
        """Open a wrapped `V31` session and verify the lane really became wrapped."""
        compare_material = self.compare_material
        if compare_material is None:
            compare_material = endpoint.v31_compare_material

        request = format_account_frame(endpoint.normalized_account, build_v31_auth_body(compare_material))
        raw_reply = await transport.exchange(request, payload_required())

        # Denials arrive as plain replies. Only a successful reply enters the
        # wrapped traffic format, so any denial ends the handshake here.
        denials = extract_v_denials(raw_reply)
        if denials:
            raise SessionHandshakeError(
                f"V31 authentication denied by panel ({denials[0].decode('ascii')})"
            )

        try:
            normalized_reply, _wrapped = normalize_wrapped_reply(raw_reply)
        except ValueError as exc:
            raise SessionHandshakeError("V31 authentication reply was not recognized") from exc

        if b"+V3" not in normalized_reply:
            raise SessionHandshakeError("V31 authentication reply was not recognized")

        return SessionState(mode=self.mode, metadata={"auth_reply": normalized_reply, "auth_denial_code": None, "compare_material": compare_material or ""})

    async def close(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
    ) -> None:
        del state
        await _close_wrapped_v3_session(endpoint, transport)

    async def execute(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
        transaction: Transaction,
    ) -> Transaction:
        del state
        return await _execute_wrapped_v3_transaction(endpoint, transport, self.mode, transaction)


@dataclass(slots=True)
class SessionProfileV30:
    """Wrapped local `V30` session profile.

    `V30` uses user-code based compare material but otherwise behaves like the
    other wrapped local sessions once it is open.
    """

    code: str | None = None
    panel_serial: str | None = None
    tail4: str | None = None
    mode: SessionMode = SessionMode.V30

    async def open(self, endpoint: PanelEndpoint, transport: TransportProtocol) -> SessionState:
        """Open a wrapped `V30` session using the configured code and panel serial."""
        code = self.code or endpoint.user_code
        panel_serial = self.panel_serial or endpoint.panel_serial
        tail4 = self.tail4 or endpoint.v30_tail4 or "0000"

        if not code:
            raise SessionHandshakeError("V30 requires a user code")
        if not panel_serial:
            raise SessionHandshakeError("V30 requires a panel serial")

        request = format_account_frame(endpoint.normalized_account, build_v30_auth_body(endpoint.normalized_account, panel_serial, code, tail4))
        raw_reply = await transport.exchange(request, payload_required())

        # Denials arrive as plain replies. Only a successful reply enters the
        # wrapped traffic format, so any denial ends the handshake here.
        denials = extract_v_denials(raw_reply)
        if denials:
            raise SessionHandshakeError(
                f"V30 authentication denied by panel ({denials[0].decode('ascii')})"
            )

        try:
            normalized_reply, _wrapped = normalize_wrapped_reply(raw_reply)
        except ValueError as exc:
            raise SessionHandshakeError("V30 authentication reply was not recognized") from exc

        if b"+V3" not in normalized_reply:
            raise SessionHandshakeError("V30 authentication reply was not recognized")

        return SessionState(mode=self.mode, metadata={"auth_reply": normalized_reply, "auth_denial_code": None, "code": code, "panel_serial": panel_serial, "tail4": tail4})

    async def close(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
    ) -> None:
        del state
        await _close_wrapped_v3_session(endpoint, transport)

    async def execute(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
        transaction: Transaction,
    ) -> Transaction:
        del state
        return await _execute_wrapped_v3_transaction(endpoint, transport, self.mode, transaction)


@dataclass(slots=True)
class SessionProfileSecureS:
    """Secure local Integrator passphrase session profile.

    This profile wraps every logical command in the `!!S` framing layer and
    keeps the rolling sequence numbers in session metadata between exchanges.
    """

    passphrase: str | None = None
    mode: SessionMode = SessionMode.SECURE_S

    async def open(self, endpoint: PanelEndpoint, transport: TransportProtocol) -> SessionState:
        """Open a secure `!!S` session and capture the starting sequence state."""
        passphrase = self.passphrase or endpoint.passphrase
        if not passphrase:
            raise SessionHandshakeError("Secure !!S requires a passphrase")

        client_seq = 0
        client_ack = 0
        request = build_secure_s_setup_frame(passphrase, seq=client_seq, ack=client_ack)
        raw_reply = await transport.exchange(request, payload_required())

        if raw_reply == SECURE_S_PREFIX:
            raise SessionHandshakeError("Secure !!S setup returned bare !!S")

        try:
            reply = parse_secure_s_frame(passphrase, raw_reply)
        except ValueError as exc:
            raise SessionHandshakeError("Secure !!S setup reply was not recognized") from exc

        if reply.frame_type != SECURE_S_FRAME_TYPE_SETUP_REPLY:
            raise SessionHandshakeError("Secure !!S setup reply had the wrong frame type")

        expected_ack = expected_secure_s_setup_reply_ack(client_seq)
        if reply.ack != expected_ack:
            raise SessionHandshakeError(
                f"Secure !!S setup reply ACK mismatch: got 0x{reply.ack:04X}, expected 0x{expected_ack:04X}"
            )

        return SessionState(mode=self.mode, metadata={"passphrase": passphrase, "next_send_seq": next_secure_s_send_sequence(client_seq, 7), "next_send_ack": (reply.seq + reply.logical_length) & 0xFFFF, "setup_reply": raw_reply})

    async def close(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
    ) -> None:
        """Secure `!!S` does not need an explicit close command."""
        del endpoint, transport, state

    async def execute(
        self,
        endpoint: PanelEndpoint,
        transport: TransportProtocol,
        state: SessionState,
        transaction: Transaction,
    ) -> Transaction:
        """Wrap one logical transaction inside secure `!!S` framing."""
        passphrase = state.metadata.get("passphrase")

        if not isinstance(passphrase, str) or not passphrase:
            raise SessionProtocolError("Secure !!S session is missing a passphrase")

        async def exchange(body: bytes | str, completion) -> TransactionExchangeResult:
            next_send_seq = state.metadata.get("next_send_seq")
            next_send_ack = state.metadata.get("next_send_ack")
            if not isinstance(next_send_seq, int) or not isinstance(next_send_ack, int):
                raise SessionProtocolError("Secure !!S session is missing sequence state")

            # Secure `!!S` wraps the same logical command we would otherwise
            # send on a clear socket. We build that clear payload first, then
            # wrap it.
            logical_payload = format_account_frame(endpoint.normalized_account, body)
            logical_length = 7 + len(logical_payload)
            wire_request = build_secure_s_frame(passphrase, seq=next_send_seq, ack=next_send_ack, frame_type=SECURE_S_FRAME_TYPE_DATA, payload=logical_payload)
            raw_reply = await transport.exchange(wire_request, completion)

            # We always advance our outgoing sequence after we send a frame.
            # That way the next transaction starts from the updated state.
            state.metadata["next_send_seq"] = next_secure_s_send_sequence(next_send_seq, logical_length)

            if not raw_reply:
                return TransactionExchangeResult(wire_request=wire_request, response=None, wire_response=None)

            if raw_reply == SECURE_S_PREFIX:
                raise SessionProtocolError("Secure !!S data exchange returned bare !!S")

            try:
                reply = parse_secure_s_frame(passphrase, raw_reply)
            except ValueError as exc:
                raise SessionProtocolError("Secure !!S data reply was not recognized") from exc

            if reply.frame_type != SECURE_S_FRAME_TYPE_DATA:
                raise SessionProtocolError("Secure !!S data reply had the wrong frame type")

            # The reply tells us what the panel expects us to acknowledge on
            # the next frame.
            state.metadata["next_send_ack"] = (reply.seq + reply.logical_length) & 0xFFFF
            return TransactionExchangeResult(wire_request=wire_request, response=reply.payload, wire_response=raw_reply)

        return await transaction.execute_in_session(exchange, session_mode=self.mode, endpoint=endpoint)


def build_session_profile(mode: SessionMode, **kwargs: str) -> SessionProfile:
    """Create the matching profile object for a selected session mode."""
    if mode is SessionMode.BLANK_V2:
        return SessionProfileBlankV2()
    if mode is SessionMode.KEYED_V2:
        return SessionProfileKeyedV2(remote_key=kwargs.get("remote_key", ""))
    if mode is SessionMode.V31:
        return SessionProfileV31(compare_material=kwargs.get("compare_material"))
    if mode is SessionMode.V30:
        return SessionProfileV30(
            code=kwargs.get("code"),
            panel_serial=kwargs.get("panel_serial"),
            tail4=kwargs.get("tail4"),
        )
    if mode is SessionMode.SECURE_S:
        return SessionProfileSecureS(passphrase=kwargs.get("passphrase", ""))
    raise ValueError(f"Unsupported session mode: {mode}")
