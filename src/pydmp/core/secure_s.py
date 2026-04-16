"""Secure `!!S` transport helpers for the stateless core.

This module follows the bench-confirmed local Integrator passphrase transport
documented in `Working Python Examples/dmp_secure_transport.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Final

from .wrapped_v3 import aes128_decrypt_block, aes128_encrypt_block


SECURE_S_PREFIX: Final[bytes] = b"!!S"
SECURE_S_KEY_SALT_16: Final[bytes] = bytes.fromhex("AA10999D0A5001672C5D585BA6FC65A1")

SECURE_S_FRAME_TYPE_SETUP: Final[int] = 0x02
SECURE_S_FRAME_TYPE_SETUP_REPLY: Final[int] = 0x12
SECURE_S_FRAME_TYPE_DATA: Final[int] = 0x18


@dataclass(slots=True)
class SecureSLogicalFrame:
    """One decrypted secure logical frame."""

    seq: int
    ack: int
    frame_type: int
    logical_length: int
    payload: bytes
    padded_plaintext: bytes
    ciphertext: bytes


@dataclass(slots=True)
class SecureSReplyState:
    """Sequence state for secure inbound push replies."""

    next_send_seq: int
    next_send_ack: int


def normalize_secure_s_passphrase_slot(passphrase: str | bytes) -> bytes:
    """Return the 16-byte passphrase slot used by the secure transport."""
    if isinstance(passphrase, str):
        try:
            passphrase_bytes = passphrase.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("Secure passphrase must be ASCII") from exc
    else:
        passphrase_bytes = passphrase

    if len(passphrase_bytes) > 16:
        raise ValueError(f"Secure passphrase exceeds 16 bytes: {passphrase!r}")

    return passphrase_bytes.ljust(16, b" ")


def derive_secure_s_transport_key(passphrase: str | bytes) -> bytes:
    """Derive the AES transport key from the configured passphrase."""
    slot16 = normalize_secure_s_passphrase_slot(passphrase)
    return hashlib.md5(SECURE_S_KEY_SALT_16 + slot16).digest()


def build_secure_s_logical_body(
    seq: int,
    ack: int,
    frame_type: int,
    payload: bytes = b"",
) -> bytes:
    """Build one decrypted logical frame body before AES encryption."""
    if not 0 <= seq <= 0xFFFF:
        raise ValueError(f"Secure sequence out of range: {seq!r}")
    if not 0 <= ack <= 0xFFFF:
        raise ValueError(f"Secure ack out of range: {ack!r}")
    if not 0 <= frame_type <= 0xFF:
        raise ValueError(f"Secure frame type out of range: {frame_type!r}")

    logical_length = 7 + len(payload)
    if logical_length > 0xFFFF:
        raise ValueError(f"Secure logical body too large: {logical_length}")

    return (
        seq.to_bytes(2, "little")
        + ack.to_bytes(2, "little")
        + bytes([frame_type])
        + logical_length.to_bytes(2, "little")
        + payload
    )


def _pad_secure_s_logical_body(logical_body: bytes) -> bytes:
    remainder = len(logical_body) % 16
    if remainder == 0:
        return logical_body
    return logical_body + (b"\x00" * (16 - remainder))


def encrypt_secure_s_logical_body(passphrase: str | bytes, logical_body: bytes) -> bytes:
    """Encrypt one logical body into the secure wire ciphertext."""
    key = derive_secure_s_transport_key(passphrase)
    padded = _pad_secure_s_logical_body(logical_body)
    out = bytearray()

    for offset in range(0, len(padded), 16):
        out.extend(aes128_encrypt_block(key, padded[offset:offset + 16]))

    return bytes(out)


def decrypt_secure_s_logical_body(passphrase: str | bytes, ciphertext: bytes) -> bytes:
    """Decrypt one secure ciphertext into the padded logical body."""
    if len(ciphertext) % 16 != 0:
        raise ValueError("Secure ciphertext length must be a multiple of 16 bytes")

    key = derive_secure_s_transport_key(passphrase)
    out = bytearray()

    for offset in range(0, len(ciphertext), 16):
        out.extend(aes128_decrypt_block(key, ciphertext[offset:offset + 16]))

    return bytes(out)


def build_secure_s_frame(
    passphrase: str | bytes,
    seq: int,
    ack: int,
    frame_type: int,
    payload: bytes = b"",
) -> bytes:
    """Build one full secure wire frame."""
    logical_body = build_secure_s_logical_body(seq, ack, frame_type, payload)
    ciphertext = encrypt_secure_s_logical_body(passphrase, logical_body)
    return SECURE_S_PREFIX + ciphertext


def build_secure_s_setup_frame(passphrase: str | bytes, seq: int = 0, ack: int = 0) -> bytes:
    """Build the secure setup frame sent at session start."""
    return build_secure_s_frame(
        passphrase,
        seq=seq,
        ack=ack,
        frame_type=SECURE_S_FRAME_TYPE_SETUP,
        payload=b"",
    )


def parse_secure_s_frame(passphrase: str | bytes, frame_bytes: bytes) -> SecureSLogicalFrame:
    """Decrypt and parse one secure wire frame."""
    if not frame_bytes.startswith(SECURE_S_PREFIX):
        raise ValueError(f"Secure frame must start with {SECURE_S_PREFIX!r}")

    ciphertext = frame_bytes[len(SECURE_S_PREFIX):]
    padded_plaintext = decrypt_secure_s_logical_body(passphrase, ciphertext)
    if len(padded_plaintext) < 7:
        raise ValueError("Secure logical frame is shorter than the 7-byte header")

    seq = int.from_bytes(padded_plaintext[0:2], "little")
    ack = int.from_bytes(padded_plaintext[2:4], "little")
    frame_type = padded_plaintext[4]
    logical_length = int.from_bytes(padded_plaintext[5:7], "little")

    if logical_length < 7:
        raise ValueError(f"Secure logical length is invalid: {logical_length}")
    if logical_length > len(padded_plaintext):
        raise ValueError(
            f"Secure logical length {logical_length} exceeds decrypted body {len(padded_plaintext)}"
        )

    return SecureSLogicalFrame(
        seq=seq,
        ack=ack,
        frame_type=frame_type,
        logical_length=logical_length,
        payload=padded_plaintext[7:logical_length],
        padded_plaintext=padded_plaintext,
        ciphertext=ciphertext,
    )


def expected_secure_s_setup_reply_ack(client_seq: int) -> int:
    """Return the setup ACK value the panel should send back."""
    if not 0 <= client_seq <= 0xFFFF:
        raise ValueError(f"Secure sequence out of range: {client_seq!r}")
    return (client_seq + 7) & 0xFFFF


def next_secure_s_send_sequence(current_seq: int, logical_length: int) -> int:
    """Advance the next client send sequence after one logical frame."""
    if not 0 <= current_seq <= 0xFFFF:
        raise ValueError(f"Secure sequence out of range: {current_seq!r}")
    if not 0 <= logical_length <= 0xFFFF:
        raise ValueError(f"Secure logical length out of range: {logical_length!r}")
    return (current_seq + logical_length) & 0xFFFF


def next_expected_secure_s_ack(frame: SecureSLogicalFrame) -> int:
    """Return the ACK value that should be sent after one incoming frame."""
    return (frame.seq + frame.logical_length) & 0xFFFF


def peek_secure_s_frame_length(passphrase: str | bytes, buffer: bytes) -> int | None:
    """Return the total wire length for one secure frame when enough header exists."""
    minimum = len(SECURE_S_PREFIX) + 16
    if len(buffer) < minimum:
        return None
    if not buffer.startswith(SECURE_S_PREFIX):
        raise ValueError(f"Secure frame must start with {SECURE_S_PREFIX!r}")

    first_block = buffer[len(SECURE_S_PREFIX):minimum]
    first_plaintext = decrypt_secure_s_logical_body(passphrase, first_block)
    if len(first_plaintext) < 7:
        raise ValueError("Secure first block is shorter than the 7-byte logical header")

    logical_length = int.from_bytes(first_plaintext[5:7], "little")
    if logical_length < 7:
        raise ValueError(f"Secure logical length is invalid: {logical_length}")
    if logical_length > 0x4000:
        raise ValueError(f"Secure logical length is unreasonably large: {logical_length}")

    ciphertext_length = ((logical_length + 15) // 16) * 16
    return len(SECURE_S_PREFIX) + ciphertext_length


def build_secure_s_push_ack_payload(account: str | int) -> bytes:
    """Build the inner clear ACK payload used for secure inbound pushes."""
    digits = str(account).strip()
    if not digits.isdigit() or not 1 <= len(digits) <= 5:
        raise ValueError(f"Account must be 1..5 digits: {account!r}")
    return b"\x02" + digits.rjust(5).encode("ascii") + b"\x06\r"


def build_secure_s_setup_reply_frame(
    passphrase: str | bytes,
    incoming_setup: SecureSLogicalFrame,
    *,
    server_seq: int,
) -> tuple[bytes, SecureSReplyState]:
    """Build the secure setup reply expected by the panel."""
    if incoming_setup.frame_type != SECURE_S_FRAME_TYPE_SETUP:
        raise ValueError(
            f"Secure setup reply requires incoming type 0x02, got 0x{incoming_setup.frame_type:02X}"
        )
    if incoming_setup.logical_length != 7:
        raise ValueError(
            "Secure setup reply requires incoming logical length 7, "
            f"got {incoming_setup.logical_length}"
        )

    reply_ack = next_expected_secure_s_ack(incoming_setup)
    wire = build_secure_s_frame(
        passphrase,
        seq=server_seq,
        ack=reply_ack,
        frame_type=SECURE_S_FRAME_TYPE_SETUP_REPLY,
        payload=b"",
    )
    return (
        wire,
        SecureSReplyState(
            next_send_seq=next_secure_s_send_sequence(server_seq, 7),
            next_send_ack=reply_ack,
        ),
    )


def build_secure_s_data_frame_from_state(
    passphrase: str | bytes,
    state: SecureSReplyState,
    payload: bytes,
) -> bytes:
    """Build one secure data frame and advance the reply sequence state."""
    logical_length = 7 + len(payload)
    wire = build_secure_s_frame(
        passphrase,
        seq=state.next_send_seq,
        ack=state.next_send_ack,
        frame_type=SECURE_S_FRAME_TYPE_DATA,
        payload=payload,
    )
    state.next_send_seq = next_secure_s_send_sequence(state.next_send_seq, logical_length)
    return wire


def build_secure_s_push_ack_frame(
    passphrase: str | bytes,
    state: SecureSReplyState,
    *,
    account: str | int,
    incoming_push: SecureSLogicalFrame,
) -> bytes:
    """Build the secure data-frame ACK for one inbound secure push."""
    if incoming_push.frame_type != SECURE_S_FRAME_TYPE_DATA:
        raise ValueError(
            f"Secure push ACK requires incoming type 0x18, got 0x{incoming_push.frame_type:02X}"
        )
    state.next_send_ack = next_expected_secure_s_ack(incoming_push)
    return build_secure_s_data_frame_from_state(
        passphrase,
        state,
        build_secure_s_push_ack_payload(account),
    )
