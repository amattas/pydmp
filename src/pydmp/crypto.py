"""LFSR-based encryption for DMP user codes.

DMP uses a Linear Feedback Shift Register (LFSR) algorithm for encrypting
user codes in certain commands. The algorithm is symmetric (encrypt = decrypt).
"""

from typing import Final


class DMPCrypto:
    """LFSR encryption for DMP user codes."""

    # Control string defines which characters to encrypt and how
    # '-' = skip, '2' = 2-char hex, '3' = 3-digit decimal
    LFSR_CONTROL_STRING: Final[str] = "----2222222223333"

    def __init__(self, account_number: int, remote_key: str = ""):
        """Initialize crypto with account number and optional remote key.

        Args:
            account_number: 5-digit account number (1-99999)
            remote_key: Remote key for authentication (not used for Entree connections)
        """
        if not 1 <= account_number <= 99999:
            raise ValueError("Account number must be between 1 and 99999")

        self.account_number = account_number
        self.remote_key = remote_key
        self._seed = 0

    def _generate_seed(self, user_code: str) -> int:
        """Generate LFSR seed from user code.

        Args:
            user_code: 4-6 digit user code

        Returns:
            8-bit seed value
        """
        # Extract first 4 digits of user code
        code_int = int(user_code[:4])

        # Base seed: (account + code) & 0xFF
        base_seed = (self.account_number + code_int) & 0xFF

        # System seed (for remote link)
        # For remote: system_seed = remote_key[0:2] XOR remote_key[6:8]
        system_seed = 0
        rk = (self.remote_key or "")
        if len(rk) >= 8:
            try:
                a = int(rk[0:2], 16)
                b = int(rk[6:8], 16)
                system_seed = a ^ b
            except ValueError:
                system_seed = 0

        # Final seed
        final_seed = base_seed ^ system_seed
        return final_seed

    def _perform_lfsr(self) -> int:
        """Perform one LFSR iteration.

        Returns:
            Next 8-bit LFSR value
        """
        seed = self._seed

        # Extract bits for XOR feedback
        bit0 = seed & 1
        bit2 = (seed >> 2) & 1
        bit3 = (seed >> 3) & 1
        bit4 = (seed >> 4) & 1

        # Calculate feedback bit
        bit_val = bit0 ^ bit2 ^ bit3 ^ bit4

        # Shift right and insert feedback at MSB
        seed = seed >> 1
        if bit_val == 1:
            seed |= 0x80

        # Handle zero case
        if seed == 0:
            seed = 255

        self._seed = seed
        return seed

    def encrypt_string(self, string_to_encrypt: str) -> str:
        """Encrypt a string using LFSR algorithm.

        The control string determines which positions are encrypted:
        - '-': Skip (no encryption)
        - '2': Encrypt 2-char hex value
        - '3': Encrypt 3-digit decimal value

        Args:
            string_to_encrypt: String to encrypt (typically user code + data)

        Returns:
            Encrypted string
        """
        # Generate seed from first 4 characters (user code)
        self._seed = self._generate_seed(string_to_encrypt[:4])

        result = list(string_to_encrypt)
        string_pos = 0

        for control_char in self.LFSR_CONTROL_STRING:
            if string_pos >= len(result):
                break

            if control_char == "3":
                # Encrypt 3-digit decimal
                if string_pos + 3 <= len(result):
                    work_num = int("".join(result[string_pos : string_pos + 3]))
                    work_num = (work_num & 0xFF) ^ self._perform_lfsr()
                    encrypted = f"{work_num:03d}"
                    result[string_pos : string_pos + 3] = encrypted
                    string_pos += 3

            elif control_char == "2":
                # Encrypt 2-char hex
                if string_pos + 2 <= len(result):
                    work_num = int("".join(result[string_pos : string_pos + 2]), 16)
                    work_num = work_num ^ self._perform_lfsr()
                    encrypted = f"{work_num:02X}"
                    result[string_pos : string_pos + 2] = encrypted
                    string_pos += 2

            elif control_char == "H":
                # Encrypt high nibble
                if string_pos + 1 <= len(result):
                    work_num = int(result[string_pos], 16)
                    work_num = work_num ^ self._perform_lfsr()
                    work_num = (work_num >> 4) & 0x0F
                    result[string_pos] = f"{work_num:X}"
                    string_pos += 1

            elif control_char == "L":
                # Encrypt low nibble
                if string_pos + 1 <= len(result):
                    work_num = int(result[string_pos], 16)
                    work_num = work_num ^ self._perform_lfsr()
                    work_num = work_num & 0x0F
                    result[string_pos] = f"{work_num:X}"
                    string_pos += 1

            else:  # '-' or unknown
                # Skip this position
                string_pos += 1

        return "".join(result)

    def decrypt_string(self, string_to_decrypt: str) -> str:
        """Decrypt a string using LFSR algorithm.

        Since LFSR XOR is symmetric, decryption is identical to encryption.

        Args:
            string_to_decrypt: String to decrypt

        Returns:
            Decrypted string
        """
        return self.encrypt_string(string_to_decrypt)

    def encrypt_user_code(self, user_code: str) -> str:
        """Encrypt a user code for use in disarm commands.

        Args:
            user_code: 4-6 digit user code

        Returns:
            Encrypted user code
        """
        if not user_code.isdigit() or not 4 <= len(user_code) <= 6:
            raise ValueError("User code must be 4-6 digits")

        # Pad to 6 digits if needed
        padded_code = user_code.ljust(6, "0")

        # For disarm command, we encrypt the entire code
        # Control string is applied to the formatted string
        return self.encrypt_string(padded_code)
