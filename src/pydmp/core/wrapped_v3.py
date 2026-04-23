"""Wrapped local V3 helpers used by the stateless core.

This module only carries the pieces needed for the current core:
- local `!V31` auth payload formatting
- local `!V30` token building
- wrapped request framing
- wrapped reply unwrapping
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib


HEX_DIGITS = "0123456789ABCDEF"
V3_TRAILER_SPACE = 0x20
V31_COMPARE_WIDTH = 10

AES_SBOX = (
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
)
AES_INV_SBOX = (
    0x52, 0x09, 0x6A, 0xD5, 0x30, 0x36, 0xA5, 0x38, 0xBF, 0x40, 0xA3, 0x9E, 0x81, 0xF3, 0xD7, 0xFB,
    0x7C, 0xE3, 0x39, 0x82, 0x9B, 0x2F, 0xFF, 0x87, 0x34, 0x8E, 0x43, 0x44, 0xC4, 0xDE, 0xE9, 0xCB,
    0x54, 0x7B, 0x94, 0x32, 0xA6, 0xC2, 0x23, 0x3D, 0xEE, 0x4C, 0x95, 0x0B, 0x42, 0xFA, 0xC3, 0x4E,
    0x08, 0x2E, 0xA1, 0x66, 0x28, 0xD9, 0x24, 0xB2, 0x76, 0x5B, 0xA2, 0x49, 0x6D, 0x8B, 0xD1, 0x25,
    0x72, 0xF8, 0xF6, 0x64, 0x86, 0x68, 0x98, 0x16, 0xD4, 0xA4, 0x5C, 0xCC, 0x5D, 0x65, 0xB6, 0x92,
    0x6C, 0x70, 0x48, 0x50, 0xFD, 0xED, 0xB9, 0xDA, 0x5E, 0x15, 0x46, 0x57, 0xA7, 0x8D, 0x9D, 0x84,
    0x90, 0xD8, 0xAB, 0x00, 0x8C, 0xBC, 0xD3, 0x0A, 0xF7, 0xE4, 0x58, 0x05, 0xB8, 0xB3, 0x45, 0x06,
    0xD0, 0x2C, 0x1E, 0x8F, 0xCA, 0x3F, 0x0F, 0x02, 0xC1, 0xAF, 0xBD, 0x03, 0x01, 0x13, 0x8A, 0x6B,
    0x3A, 0x91, 0x11, 0x41, 0x4F, 0x67, 0xDC, 0xEA, 0x97, 0xF2, 0xCF, 0xCE, 0xF0, 0xB4, 0xE6, 0x73,
    0x96, 0xAC, 0x74, 0x22, 0xE7, 0xAD, 0x35, 0x85, 0xE2, 0xF9, 0x37, 0xE8, 0x1C, 0x75, 0xDF, 0x6E,
    0x47, 0xF1, 0x1A, 0x71, 0x1D, 0x29, 0xC5, 0x89, 0x6F, 0xB7, 0x62, 0x0E, 0xAA, 0x18, 0xBE, 0x1B,
    0xFC, 0x56, 0x3E, 0x4B, 0xC6, 0xD2, 0x79, 0x20, 0x9A, 0xDB, 0xC0, 0xFE, 0x78, 0xCD, 0x5A, 0xF4,
    0x1F, 0xDD, 0xA8, 0x33, 0x88, 0x07, 0xC7, 0x31, 0xB1, 0x12, 0x10, 0x59, 0x27, 0x80, 0xEC, 0x5F,
    0x60, 0x51, 0x7F, 0xA9, 0x19, 0xB5, 0x4A, 0x0D, 0x2D, 0xE5, 0x7A, 0x9F, 0x93, 0xC9, 0x9C, 0xEF,
    0xA0, 0xE0, 0x3B, 0x4D, 0xAE, 0x2A, 0xF5, 0xB0, 0xC8, 0xEB, 0xBB, 0x3C, 0x83, 0x53, 0x99, 0x61,
    0x17, 0x2B, 0x04, 0x7E, 0xBA, 0x77, 0xD6, 0x26, 0xE1, 0x69, 0x14, 0x63, 0x55, 0x21, 0x0C, 0x7D,
)
AES_RCON = (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


@dataclass(slots=True)
class WrappedV3Body:
    """One wrapped local V3 body after checksum parse."""

    body: bytes
    trailer_byte: int
    checksum: int


def _ensure_ascii_bytes(value: str | bytes, label: str) -> bytes:
    """Return ASCII bytes for a helper input that may start as text."""
    if isinstance(value, bytes):
        return value
    try:
        return value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must be ASCII") from exc


def _normalize_trailer_byte(trailer_byte: str | bytes | int) -> int:
    """Normalize the single-byte trailer used by wrapped V3 messages."""
    if isinstance(trailer_byte, int):
        if 0 <= trailer_byte <= 0xFF:
            return trailer_byte
        raise ValueError(f"Trailer byte out of range: {trailer_byte!r}")

    trailer_bytes = _ensure_ascii_bytes(trailer_byte, "Trailer byte")
    if len(trailer_bytes) != 1:
        raise ValueError(f"Trailer byte must be exactly 1 byte: {trailer_byte!r}")
    return trailer_bytes[0]


def normalize_v31_material(compare_material: str | bytes | None) -> str:
    """Return the local `!V31` compare field padded to the 10-byte wire width."""
    compare_bytes = _ensure_ascii_bytes(compare_material or "", "V31 compare material")
    if len(compare_bytes) > V31_COMPARE_WIDTH:
        raise ValueError("V31 compare material must be at most 10 ASCII bytes")
    return compare_bytes.decode("ascii").ljust(V31_COMPARE_WIDTH)


def build_v31_auth_body(compare_material: str | bytes | None = None) -> str:
    """Build a local `!V31` auth payload."""
    return "!V31" + normalize_v31_material(compare_material)


def normalize_panel_serial(panel_serial: str | bytes) -> str:
    """Return the 8-hex panel serial field used in local `!V30` keying."""
    if isinstance(panel_serial, bytes):
        panel_text = panel_serial.decode("ascii")
    else:
        panel_text = panel_serial
    normalized = panel_text.strip().upper()
    if len(normalized) != 8 or any(char not in HEX_DIGITS for char in normalized):
        raise ValueError(f"Panel serial must be exactly 8 uppercase hex chars: {panel_serial!r}")
    return normalized


def build_v30_code_field12(code: str | bytes) -> bytes:
    """Build the 12-byte right-aligned code field used by the current local `!V30` model."""
    code_bytes = _ensure_ascii_bytes(code, "V30 code").strip()
    if not code_bytes or any(byte < 0x30 or byte > 0x39 for byte in code_bytes):
        raise ValueError(f"V30 code must be numeric: {code!r}")
    if len(code_bytes) > 12:
        raise ValueError(f"V30 code must be 1..12 digits: {code!r}")
    return code_bytes.rjust(12, b" ")


def normalize_v30_tail4(tail4: str | bytes | None) -> bytes:
    """Return the 4-byte tail field for local `!V30`."""
    tail_bytes = _ensure_ascii_bytes(tail4 or "0000", "V30 tail4")
    if len(tail_bytes) != 4:
        raise ValueError(f"V30 tail4 must be exactly 4 ASCII bytes: {tail4!r}")
    return tail_bytes


def build_v30_plaintext_block(code: str | bytes, tail4: str | bytes | None = None) -> bytes:
    """Build the 16-byte plaintext block encrypted into the `!V30` token."""
    return build_v30_code_field12(code) + normalize_v30_tail4(tail4)


def _sub_word(word_value: int) -> int:
    return (
        (AES_SBOX[(word_value >> 24) & 0xFF] << 24)
        | (AES_SBOX[(word_value >> 16) & 0xFF] << 16)
        | (AES_SBOX[(word_value >> 8) & 0xFF] << 8)
        | AES_SBOX[word_value & 0xFF]
    )


def _rot_word(word_value: int) -> int:
    return ((word_value << 8) & 0xFFFFFFFF) | ((word_value >> 24) & 0xFF)


def _expand_aes128_key(key_bytes: bytes) -> list[bytes]:
    if len(key_bytes) != 16:
        raise ValueError(f"AES-128 key must be exactly 16 bytes: {key_bytes!r}")

    words = [int.from_bytes(key_bytes[index:index + 4], "big") for index in range(0, 16, 4)]
    for word_index in range(4, 44):
        temp = words[word_index - 1]
        if word_index % 4 == 0:
            temp = _sub_word(_rot_word(temp)) ^ (AES_RCON[word_index // 4] << 24)
        words.append(words[word_index - 4] ^ temp)

    return [
        b"".join(words[start + offset].to_bytes(4, "big") for offset in range(4))
        for start in range(0, 44, 4)
    ]


def _gf_mul(byte_value: int, factor: int) -> int:
    result = 0
    work = byte_value
    mult = factor
    while mult:
        if mult & 1:
            result ^= work
        work = ((work << 1) ^ 0x1B) & 0xFF if work & 0x80 else (work << 1) & 0xFF
        mult >>= 1
    return result


def _add_round_key(state: list[int], round_key: bytes) -> None:
    for index, key_byte in enumerate(round_key):
        state[index] ^= key_byte


def _sub_bytes(state: list[int]) -> None:
    for index, value in enumerate(state):
        state[index] = AES_SBOX[value]


def _inv_sub_bytes(state: list[int]) -> None:
    for index, value in enumerate(state):
        state[index] = AES_INV_SBOX[value]


def _shift_rows(state: list[int]) -> None:
    state[1], state[5], state[9], state[13] = state[5], state[9], state[13], state[1]
    state[2], state[6], state[10], state[14] = state[10], state[14], state[2], state[6]
    state[3], state[7], state[11], state[15] = state[15], state[3], state[7], state[11]


def _inv_shift_rows(state: list[int]) -> None:
    state[1], state[5], state[9], state[13] = state[13], state[1], state[5], state[9]
    state[2], state[6], state[10], state[14] = state[10], state[14], state[2], state[6]
    state[3], state[7], state[11], state[15] = state[7], state[11], state[15], state[3]


def _mix_columns(state: list[int]) -> None:
    for column_index in range(4):
        offset = column_index * 4
        s0, s1, s2, s3 = state[offset:offset + 4]
        state[offset + 0] = _gf_mul(s0, 2) ^ _gf_mul(s1, 3) ^ s2 ^ s3
        state[offset + 1] = s0 ^ _gf_mul(s1, 2) ^ _gf_mul(s2, 3) ^ s3
        state[offset + 2] = s0 ^ s1 ^ _gf_mul(s2, 2) ^ _gf_mul(s3, 3)
        state[offset + 3] = _gf_mul(s0, 3) ^ s1 ^ s2 ^ _gf_mul(s3, 2)


def _inv_mix_columns(state: list[int]) -> None:
    for column_index in range(4):
        offset = column_index * 4
        s0, s1, s2, s3 = state[offset:offset + 4]
        state[offset + 0] = (
            _gf_mul(s0, 0x0E) ^ _gf_mul(s1, 0x0B) ^ _gf_mul(s2, 0x0D) ^ _gf_mul(s3, 0x09)
        )
        state[offset + 1] = (
            _gf_mul(s0, 0x09) ^ _gf_mul(s1, 0x0E) ^ _gf_mul(s2, 0x0B) ^ _gf_mul(s3, 0x0D)
        )
        state[offset + 2] = (
            _gf_mul(s0, 0x0D) ^ _gf_mul(s1, 0x09) ^ _gf_mul(s2, 0x0E) ^ _gf_mul(s3, 0x0B)
        )
        state[offset + 3] = (
            _gf_mul(s0, 0x0B) ^ _gf_mul(s1, 0x0D) ^ _gf_mul(s2, 0x09) ^ _gf_mul(s3, 0x0E)
        )


def aes128_encrypt_block(key_bytes: bytes, plaintext_block: bytes) -> bytes:
    """Encrypt one block with the plain AES mode used by local `!V30`."""
    if len(plaintext_block) != 16:
        raise ValueError(f"AES plaintext block must be exactly 16 bytes: {plaintext_block!r}")

    round_keys = _expand_aes128_key(key_bytes)
    state = list(plaintext_block)
    _add_round_key(state, round_keys[0])

    for round_key in round_keys[1:10]:
        _sub_bytes(state)
        _shift_rows(state)
        _mix_columns(state)
        _add_round_key(state, round_key)

    _sub_bytes(state)
    _shift_rows(state)
    _add_round_key(state, round_keys[10])
    return bytes(state)


def aes128_decrypt_block(key_bytes: bytes, ciphertext_block: bytes) -> bytes:
    """Decrypt one block with the plain AES mode used by secure `!!S`."""
    if len(ciphertext_block) != 16:
        raise ValueError(f"AES ciphertext block must be exactly 16 bytes: {ciphertext_block!r}")

    round_keys = _expand_aes128_key(key_bytes)
    state = list(ciphertext_block)
    _add_round_key(state, round_keys[10])

    for round_index in range(9, 0, -1):
        _inv_shift_rows(state)
        _inv_sub_bytes(state)
        _add_round_key(state, round_keys[round_index])
        _inv_mix_columns(state)

    _inv_shift_rows(state)
    _inv_sub_bytes(state)
    _add_round_key(state, round_keys[0])
    return bytes(state)


def derive_v30_key(account: str, panel_serial: str | bytes) -> bytes:
    """Derive the current local `!V30` AES key from account and panel serial."""
    seed = f"{str(account).strip().rjust(5)}@{normalize_panel_serial(panel_serial)}"
    return hashlib.md5(seed.encode("ascii")).digest()


def encode_v30_token_hex(
    account: str,
    panel_serial: str | bytes,
    code: str | bytes,
    tail4: str | bytes | None = None,
) -> str:
    """Return the 32-hex local `!V30` token."""
    plaintext_block = build_v30_plaintext_block(code, tail4)
    key = derive_v30_key(account, panel_serial)
    return aes128_encrypt_block(key, plaintext_block).hex().upper()


def build_v30_auth_body(
    account: str,
    panel_serial: str | bytes,
    code: str | bytes,
    tail4: str | bytes | None = None,
) -> str:
    """Build a local `!V30` auth payload."""
    return "!V30" + encode_v30_token_hex(account, panel_serial, code, tail4)


def dmp_fletcher16(data: bytes) -> int:
    """Compute the checksum used by wrapped local V3 frames."""
    sum_a = 0
    sum_b = 0
    for byte in data:
        work = byte + sum_a
        sum_a = (work & 0xFF) + (work >> 8)
        work = sum_b + sum_a
        sum_b = (work & 0xFF) + (work >> 8)

    work = sum_a + sum_b
    folded = (work & 0xFF) + (work >> 8)
    if folded == 0xFF:
        folded = 0

    high = (0xFF - folded) & 0xFFFF

    work = high + sum_a
    low = (work & 0xFF) + (work >> 8)
    if low == 0xFF:
        low = 0

    return ((high * 0x100 - low) + 0xFF) & 0xFFFF


def wrap_v3_body(command_body: str | bytes, trailer_byte: str | bytes | int = V3_TRAILER_SPACE) -> WrappedV3Body:
    """Wrap one plaintext local V3 body with trailer and checksum."""
    body_bytes = _ensure_ascii_bytes(command_body, "Command body")
    if not body_bytes:
        raise ValueError("Command body must not be empty")
    trailer = _normalize_trailer_byte(trailer_byte)
    checksum = dmp_fletcher16(body_bytes + bytes([trailer]))
    return WrappedV3Body(body=body_bytes, trailer_byte=trailer, checksum=checksum)


def unwrap_v3_body(wrapped_body: str | bytes) -> WrappedV3Body:
    """Parse a wrapped local V3 body and verify its checksum."""
    wrapped_bytes = _ensure_ascii_bytes(wrapped_body, "Wrapped body")
    if len(wrapped_bytes) < 6:
        raise ValueError("Wrapped body is too short")

    checksum_ascii = wrapped_bytes[-4:]
    try:
        checksum_value = int(checksum_ascii.decode("ascii"), 16)
    except ValueError as exc:
        raise ValueError(f"Wrapped body has invalid checksum trailer: {wrapped_body!r}") from exc

    trailer_byte = wrapped_bytes[-5]
    body_bytes = wrapped_bytes[:-5]
    expected = dmp_fletcher16(body_bytes + bytes([trailer_byte]))
    if checksum_value != expected:
        raise ValueError(
            f"Wrapped body checksum mismatch: got {checksum_value:04X}, expected {expected:04X}"
        )

    return WrappedV3Body(body=body_bytes, trailer_byte=trailer_byte, checksum=checksum_value)


def encode_account_v3_frame(
    account: str,
    command_body: str | bytes,
    trailer_byte: str | bytes | int = V3_TRAILER_SPACE,
) -> bytes:
    """Build one wrapped local V3 request frame.

    The returned bytes already include the `@` prefix, normalized account
    field, wrapped body, checksum, and trailing carriage return.
    """
    wrapped = wrap_v3_body(command_body, trailer_byte)
    checksum_text = f"{wrapped.checksum:04X}".encode("ascii")
    return (
        b"@"
        + str(account).strip().rjust(5).encode("ascii")
        + wrapped.body
        + bytes([wrapped.trailer_byte])
        + checksum_text
        + b"\r"
    )


def extract_first_frame(raw_reply: bytes) -> bytes:
    """Return the first clean reply frame from a raw transport read.

    This helper removes common transport noise like NUL padding and leading
    STX so higher layers can work with one stable frame shape.
    """
    cleaned = raw_reply.replace(b"\x00", b"")
    if cleaned.startswith(b"\x02"):
        cleaned = cleaned[1:]
    frame, _separator, _rest = cleaned.partition(b"\r")
    if not frame:
        raise ValueError("Reply did not contain a panel frame")
    return frame + b"\r"


def normalize_plain_reply(raw_reply: bytes) -> bytes:
    """Normalize one plain local reply frame."""
    frame = extract_first_frame(raw_reply)
    if not frame.startswith(b"@"):
        raise ValueError("Reply did not start with an account frame")
    return frame


def parse_account_v3_frame(frame: str | bytes) -> tuple[str, WrappedV3Body]:
    """Parse an account-framed wrapped V3 request or reply."""
    frame_bytes = _ensure_ascii_bytes(frame, "Wrapped frame").rstrip(b"\r")
    if frame_bytes.startswith(b"\x02"):
        frame_bytes = frame_bytes[1:]
    if not frame_bytes.startswith(b"@"):
        raise ValueError("Wrapped frame did not start with '@'")

    payload = frame_bytes[1:]
    for account_length in (6, 5):
        if len(payload) <= account_length:
            continue
        account_field = payload[:account_length]
        wrapped_bytes = payload[account_length:]
        try:
            wrapped = unwrap_v3_body(wrapped_bytes)
        except ValueError:
            continue
        return account_field.decode("ascii"), wrapped

    raise ValueError("Wrapped frame account field could not be parsed")


def normalize_wrapped_reply(raw_reply: bytes) -> tuple[bytes, WrappedV3Body]:
    """Normalize one wrapped reply back into a plain parser-facing reply frame.

    Transaction parsers should not need to know whether a session was wrapped,
    so this helper returns the clear parser-facing frame alongside the parsed
    wrapped-body details.
    """
    frame = extract_first_frame(raw_reply)
    account_field, wrapped = parse_account_v3_frame(frame)
    normalized = b"@" + account_field.encode("ascii") + wrapped.body + b"\r"
    return normalized, wrapped
