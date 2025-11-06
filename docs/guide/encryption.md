# Encryption & User Data

Some user data returned by the panel (e.g., `?P=` user codes) is obfuscated with a weak LFSR algorithm. PyDMP implements the same logic used by the reference Lua driver.

## Modes

- Entrée (no remote key):
  - Seed = (account + first 4 digits of user code) & 0xFF
  - `system_seed = 0`
- Remote link (remote key present):
  - `system_seed = XOR(int(remote_key[0:2],16), int(remote_key[6:8],16))`
  - Final seed = base_seed XOR system_seed

PyDMP uses remote‑link mixing when a remote key is supplied and hex‑parsable; otherwise, it falls back to Entrée mode.

## Fetching Users & Profiles

```python
users = await panel.get_user_codes()      # Decrypts *P= replies into UserCode objects
profiles = await panel.get_user_profiles()  # Parses *U replies into UserProfile objects
```

`get_user_codes()` and `get_user_profiles()` handle paging until completion.

## Auth Note (`!V2`)

Authentication uses `!V2{remote_key}`. If you don't have a key, your panel may still accept a blank/placeholder key; otherwise configure the correct key for your installation.

