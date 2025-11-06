from dataclasses import dataclass
from typing import Tuple


@dataclass
class UserCode:
    """Decrypted user code record."""

    number: str
    code: str
    pin: str
    profiles: Tuple[str, str, str, str]
    # Historically parsed fields; see start_date/end_date for clarified meaning
    temp_date: str  # legacy 6-digit field; same as end_date (DDMMYY)
    exp_date: str   # legacy 4-char field; often '----' on observed panels
    name: str
    # Clarified/additional fields parsed from the trailing plaintext segment
    start_date: str | None = None   # 6 digits DDMMYY; start of access
    end_date: str | None = None     # 6 digits DDMMYY; end of access
    flags: str | None = None        # 3 chars (e.g., 'YNN')
    # Derived flags for clarity
    active: bool | None = None      # First Y/N flag: user active
    temporary: bool | None = None   # Third Y/N flag: temporary user

