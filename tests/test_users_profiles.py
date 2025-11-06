from pydmp.protocol import DMPProtocol, UserCodesResponse, UserProfilesResponse


def test_decode_user_codes_single_entry():
    # Build a plaintext user record and encrypt it, then wrap as *P=
    proto = DMPProtocol("1", "ABCD1234")

    # number(4)=0001, code(12)=1234FFFF0000, pin(6)=1111FF, P1..P4=001,002,003,004,
    # temp(6)=010122, exp(4)=0900, name='USER'
    plain = (
        "0001"
        + "1234FFFFFF00"[:12]
        + "1111FF"
        + "001"
        + "002"
        + "003"
        + "004"
        + "010122"
        + "0900"
        + "USER"
    )
    enc = proto.crypto.encrypt_string(plain)

    payload = f"@    1+*P={enc}\x1e\r".encode()
    resp = proto.decode_response(payload)
    assert isinstance(resp, UserCodesResponse)
    assert len(resp.users) == 1
    u = resp.users[0]
    assert u.number == "0001"
    assert u.code.startswith("1234")
    assert u.pin.startswith("1111")
    assert u.profiles[0] == "001"
    assert u.name == "USER"
    # No flags/start_date in tail -> derived fields are None
    assert u.flags is None
    assert u.active is None
    assert u.temporary is None


def test_decode_user_codes_with_flags_and_dates():
    proto = DMPProtocol("1", "ABCD1234")
    # Build record with flags (Y/N/Y), start_date and name in tail
    num = "0002"
    code = "5678FFFFFF00"[:12]
    pin = "2222FF"
    p1, p2, p3, p4 = "001", "002", "003", "004"
    end_date = "310725"  # DDMMYY
    legacy_exp = "0900"
    flags = "YNY"  # active=True, temporary=True
    start_date = "010125"
    name = "JDOE"
    plain = num + code + pin + p1 + p2 + p3 + p4 + end_date + legacy_exp + flags + start_date + name
    enc = proto.crypto.encrypt_string(plain)
    payload = f"@    1+*P={enc}\x1e\r".encode()
    resp = proto.decode_response(payload)
    assert isinstance(resp, UserCodesResponse)
    assert len(resp.users) == 1
    u = resp.users[0]
    assert u.number == num
    assert u.flags == flags
    assert u.start_date == start_date
    assert u.end_date == end_date
    assert u.active is True
    assert u.temporary is True


def test_decode_user_profiles_single_entry():
    proto = DMPProtocol("1", "")
    # Minimal profile: number 001, masks, output group, menu, rearm, name
    prof = "001" + "C3000000" + "C3000000" + "001" + "MENUOPTS" + (" " * 16) + "005" + "ADMIN"
    payload = f"@    1+*U{prof}\x1e\r".encode()
    resp = proto.decode_response(payload)
    assert isinstance(resp, UserProfilesResponse)
    assert len(resp.profiles) == 1
    p = resp.profiles[0]
    assert p.number == "001"
    assert p.name.endswith("ADMIN")
