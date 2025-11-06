# Encryption & User Data

Some user data returned by the panel (e.g., `?P=` user codes) is obfuscated with a weak LFSR algorithm. PyDMP implements the same logic used by the reference Lua driver.

## Modes

- Entrée (no remote key):
  - Seed = (account + first 4 digits of user code) & 0xFF
  - `system_seed = 0`
- Remote link (remote key present):
  - `system_seed = XOR(int(remote_key[0:2],16), int(remote_key[6:8],16))`
  - Final seed = base_seed XOR system_seed

PyDMP uses remote-link mixing when a remote key is supplied and hex-parsable; otherwise, it falls back to Entrée mode.

## Fetching Users & Profiles

```python
users = await panel.get_user_codes()      # Decrypts *P= replies into UserCode objects
profiles = await panel.get_user_profiles()  # Parses *U replies into UserProfile objects
```

`get_user_codes()` and `get_user_profiles()` handle paging until completion.

### User Codes Record Layout (*P=)

After decryption, each user record exposes:

- `number` (str): 4-digit user number
- `code` (str): up to 12 chars ("F" padding removed)
- `pin` (str): up to 6 chars ("F" padding removed)
- `profiles` (tuple[str,str,str,str]): 3-digit profile numbers ("255" = unused)
- `end_date` (str|None): 6 digits DDMMYY - end of access window
- `start_date` (str|None): 6 digits DDMMYY - start of access window (from trailing plaintext)
- `flags` (str|None): 3 letters (Y/N) - additional authorization flags
- `name` (str): user name

For backward compatibility, two legacy fields are retained:

- `temp_date` (str): same as `end_date`
- `exp_date` (str): legacy 4-char field (often "----")

Example tail parsing: a segment like `NNY310725HARDWOOD FLOORING` is split as
`flags=NNY`, `start_date=310725 (31 Jul 2025)`, `name=HARDWOOD FLOORING`.

## Auth Note (`!V2`)

Authentication uses `!V2{remote_key}`. If you don't have a key, your panel may still accept a blank/placeholder key; otherwise configure the correct key for your installation.
