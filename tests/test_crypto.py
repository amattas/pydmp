"""Tests for LFSR encryption."""

import pytest

from pydmp.crypto import DMPCrypto


class TestDMPCrypto:
    """Test LFSR encryption."""

    def test_init(self):
        """Test initialization."""
        crypto = DMPCrypto(123, "ABCD1234")
        assert crypto.account_number == 123
        assert crypto.remote_key == "ABCD1234"

    def test_init_invalid_account(self):
        """Test invalid account number."""
        with pytest.raises(ValueError, match="Account number must be between"):
            DMPCrypto(0, "")

        with pytest.raises(ValueError, match="Account number must be between"):
            DMPCrypto(100000, "")

    def test_generate_seed(self):
        """Test seed generation."""
        crypto = DMPCrypto(1, "")
        seed = crypto._generate_seed("1234")
        # Seed should be (1 + 1234) & 0xFF = 1235 & 0xFF = 211
        assert seed == 211

    def test_lfsr_iteration(self):
        """Test LFSR iteration."""
        crypto = DMPCrypto(1, "")
        crypto._seed = 0xFF  # 255
        result = crypto._perform_lfsr()
        # After LFSR: should shift and XOR bits
        assert result != 255
        assert 0 <= result <= 255

    def test_lfsr_zero_handling(self):
        """Test LFSR zero case."""
        crypto = DMPCrypto(1, "")
        # If LFSR produces 0, it should become 255
        crypto._seed = 1  # Will shift to 0 eventually
        for _ in range(10):
            result = crypto._perform_lfsr()
            assert result != 0  # Should never be 0

    def test_encrypt_decrypt_symmetric(self):
        """Test that encryption is symmetric."""
        crypto = DMPCrypto(1, "")
        plaintext = "12340000000000000"
        encrypted = crypto.encrypt_string(plaintext)
        decrypted = crypto.decrypt_string(encrypted)
        # Due to symmetric XOR nature, decrypt(encrypt(x)) = x
        assert len(encrypted) == len(plaintext)
        # Seed resets each time based on first 4 chars
        assert decrypted == plaintext

    def test_encrypt_user_code(self):
        """Test user code encryption."""
        crypto = DMPCrypto(1, "")
        code = "1234"
        encrypted = crypto.encrypt_user_code(code)
        assert len(encrypted) == 6  # Padded to 6 digits
        assert encrypted != "123400"  # Should be encrypted

    def test_encrypt_user_code_invalid(self):
        """Test invalid user code."""
        crypto = DMPCrypto(1, "")

        with pytest.raises(ValueError, match="User code must be 4-6 digits"):
            crypto.encrypt_user_code("123")  # Too short

        with pytest.raises(ValueError, match="User code must be 4-6 digits"):
            crypto.encrypt_user_code("1234567")  # Too long

        with pytest.raises(ValueError, match="User code must be 4-6 digits"):
            crypto.encrypt_user_code("abcd")  # Not digits
