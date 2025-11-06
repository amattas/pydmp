from pydmp.crypto import DMPCrypto


def test_remote_key_bad_hex_and_zero_seed():
    # Bad hex characters in remote key should not crash seed generation
    c = DMPCrypto(123, "GHxxzz99")
    # encrypt/decrypt symmetry still holds
    s = "1234ABCDEF"
    enc = c.encrypt_string(s)
    assert c.decrypt_string(enc) == s

    # Force zero seed path
    c._seed = 0
    out = c._perform_lfsr()
    assert out == 255


def test_h_l_nibble_branches(monkeypatch):
    c = DMPCrypto(1, "")
    # Patch control string to exercise H and L on two hex nibbles
    monkeypatch.setattr(DMPCrypto, "LFSR_CONTROL_STRING", "HL")
    s = "12"  # two hex chars
    # Ensure it runs and preserves length
    res = c.encrypt_string(s)
    assert isinstance(res, str) and len(res) == len(s)
