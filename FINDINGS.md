# pydmp — open findings backlog

Updated 2026-07-20. Tracks the findings still open after the `bugfix/code-review-hardening`
work (PYDMP-001..003, 006, 008..010, 015..019, 021..023 fixed and verified there — see this
file's git history for the full review, resolution ledger, and test-consolidation results).

This revision incorporates two protocol references: `commands.md` (DMP XR500 API reference,
derived from Simpl+ drivers) and `dmp.lua` (the deployed Control4 driver). PYDMP-004 and
PYDMP-005 are re-scoped; PYDMP-024..026 came out of the `commands.md` comparison and were then
cross-checked against `dmp.lua`, which materially changed two of them:
- **PYDMP-004** — both references confirm outgoing user-code encryption is dead/fictional;
  `dmp.lua` only ever *decrypts* the inbound user-code table (dmp.lua:2384). Cleanup, not behavior.
- **PYDMP-025** — downgraded to a doc conflict: `dmp.lua` sends `!O`/`!Y` with **no** trailing
  comma, matching pydmp; only `commands.md` claims a comma is required. pydmp is likely correct.
- **PYDMP-026** — strengthened: the `instant` arm flag is in **neither** reference (the earlier
  "inherited from the Lua driver" guess was wrong — dmp.lua arms with two flags). Provenance
  unknown; verify per model.

Where the two references disagree, `dmp.lua` (a working deployed driver) is the stronger
evidence; still verify against real panel hardware before changing wire behavior. Note also
that CLAUDE.md's cited `dmp.lua` line numbers are stale — the LFSR routine is at dmp.lua:1652-1725
(the file is 3124 lines), not the 3773-3955 range CLAUDE.md claims.

## Summary

| ID | Severity | Title | File(s) |
|----|----------|-------|---------|
| PYDMP-004 | Important | Dead outgoing user-code encryption; protocol doc wrong about disarm code | `crypto.py`, `transport_sync.py`, `CLAUDE.md` |
| PYDMP-005 | Important | ~1.3s latency floor — replace read-until-timeout with terminator-based read | `transport.py` |
| PYDMP-007 | Important | Reconnect leaves stale entity caches | `panel.py` |
| PYDMP-011 | Important | status_parser never maps Door-Access (`Zj`) / Service-Code (`Zm`) events | `status_parser.py` |
| PYDMP-012 | Important | Sync API parity gap | `panel_sync.py`, `area.py` |
| PYDMP-025 | Doc/close | Trailing-comma discrepancy: `commands.md` conflicts with `dmp.lua`; pydmp matches the driver | `const/commands.py` |
| PYDMP-026 | Important | Arm sends a spurious 3rd flag; 2nd flag is likely `instant`, not `force` (hass-dmp hits it) | `const/commands.py`, `panel.py` |
| PYDMP-013 | Security | S3 listener is unauthenticated with unbounded buffering | `status_server.py`, `panel.py` |
| PYDMP-014 | Security | No `\r` sanitization on values framed into commands | `protocol.py` |
| PYDMP-024 | Security | Auth response echoes the remote key into inbound debug logs | `transport.py` |
| PYDMP-020 | Quality | Dead legacy `DMPEvent` enum (~60 lines) — exported, needs deprecation path | `const/events.py` |

## Important

### PYDMP-004 — Dead outgoing user-code encryption; protocol doc wrong about disarm code

**Re-scoped by `commands.md`, then confirmed against `dmp.lua`.** Both references agree the
outgoing user-code encryption in pydmp is dead and its premise is fictional:
- `commands.md` documents disarm as `!O<AreaNumber>,\r` — no user code, no outgoing encryption.
- `dmp.lua` (the deployed Control4 driver) invokes its LFSR routine **exactly once**, at
  line 2384 inside `ReceiveUserCodes` — `encrypter.DecryptString(user)` — to *decrypt the
  inbound user-code table*. It never encrypts an outgoing command. Its disarm is a bare
  `self.Send("!O"..area)` (dmp.lua:2091) with no code and no encryption.
So pydmp's codeless disarm is correct; the CLAUDE.md protocol table (`!O[A],[CODE]`,
"Encrypted: Yes") is the thing that's wrong. pydmp's `encrypt_string`/`decrypt_string` faithfully
port the driver's LFSR (control string `----2222222223333`, seed `(account+code) & 0xFF`, taps
0/2/3/4, zero→255, symmetric) — those are correct and used for inbound decrypt. Only
`encrypt_user_code` is spurious: nothing in either reference encrypts an outgoing code, and its
docstring ("Encrypt a user code for use in disarm commands") describes a use case that does not
exist. It is also semantically wrong — it encrypts a 6-char padded code, but the control string
skips the first 4 chars (`----`), so it would only touch 2 trailing chars, unrelated to how the
panel encrypts a full user record. Remaining work is cleanup, not behavior:
- delete the never-called `DMPCrypto.encrypt_user_code` (crypto.py:170),
- remove the silently-ignored `encrypt_user_code`/`user_code` params from
  `transport_sync.send_command` (transport_sync.py:63-73),
- fix the CLAUDE.md command table.

**Impacted code**

src/pydmp/crypto.py:170-188 (never called anywhere)
```python
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
```

src/pydmp/transport_sync.py:63-73 (the `encrypt_user_code`/`user_code` params are accepted
and silently ignored)
```python
    def send_command(
        self,
        command: str,
        encrypt_user_code: bool = False,
        user_code: str | None = None,
        **kwargs: Any,
    ) -> str | StatusResponse | UserCodesResponse | UserProfilesResponse | OutputsResponse | None:
        """Send a protocol command and return decoded response."""
        encoded = self._protocol.encode_command(command, **kwargs)
        raw = self._run(self._transport.send_and_receive(encoded))
        return self._protocol.decode_response(raw)
```

commands.md (Disarm Area) — documented format has a comma field but no code:
```
!O<AreaNumber>,\r    // "Comma is required even with no parameters."
Response: \xFEA001\JOHN DOE        \MAIN LOBBY       0\xFF
```

### PYDMP-005 — ~1.3s latency floor — replace read-until-timeout with terminator-based read

`src/pydmp/transport.py:103-127`
   `_receive()` sleeps 0.3s up front, then loops reads until a 1.0s timeout — which always burns the
   full second after the last chunk because the panel keeps the connection open. `update_status()`
   issues 11 commands (~15s per refresh); `get_user_codes()` pages up to 200× (minutes).

**Re-scoped by `commands.md`**: every documented response is framed with explicit start/end
bytes (`\xFE` … `\xFF`), and multi-chunk `?WB` responses carry a deterministic continuation
marker (payload ending `-`) with `*WB-` as the end-of-list sentinel. A terminator-based read
is therefore implementable without guesswork. Caveat to verify first: pydmp's tests model
frames as `\x02` … `\r` while commands.md shows `\xFE`/`\xFF` — likely the TCP variant vs the
Crestron serial wrapper; confirm which bytes the real panel emits over TCP port 2011 and read
to that marker.

**Impacted code**

src/pydmp/transport.py:103-130
```python
    async def _receive(self) -> bytes:
        if not self._reader:
            raise DMPConnectionError("Not connected")
        try:
            # Short wait to allow response assembly
            await asyncio.sleep(RATE_LIMIT_SECONDS)
            data = b""
            while True:
                try:
                    chunk = await asyncio.wait_for(self._reader.read(4096), timeout=1.0)
                    if not chunk:
                        break
                    data += chunk
                    try:
                        _LOGGER.debug(
                            "<<< chunk %d bytes: %r",
                            len(chunk),
                            chunk.decode("utf-8", errors="replace"),
                        )
                    except Exception:
                        _LOGGER.debug("<<< chunk %d bytes: %r", len(chunk), chunk)
                except TimeoutError:
                    break
            _LOGGER.debug("<<< total %d bytes", len(data))
            return data
        except Exception as e:
            _LOGGER.error("Transport receive failed: %s", e)
            raise DMPConnectionError(f"Failed to receive data: {e}") from e
```
### PYDMP-007 — Reconnect leaves stale entity caches

`src/pydmp/panel.py:135-136`
   `_areas`/`_zones`/`_outputs` are never cleared on disconnect/connect and `update_status()` only
   merges, never prunes — reconnecting the same object to a different panel returns ghost entities.

**Impacted code**

src/pydmp/panel.py:45-50 (entity caches created once in `__init__`)
```python
        self._connection: DMPTransport | None = None
        self._protocol: DMPProtocol | None = None
        self._active_key: tuple[str, int, str] | None = None
        self._areas: dict[int, Area] = {}
        self._zones: dict[int, Zone] = {}
        self._outputs: dict[int, Output] = {}
```

src/pydmp/panel.py:115-141 (`disconnect()` — post-PYDMP-001 version — releases connection state
but still never clears the entity caches)
```python
    async def disconnect(self) -> None:
        """Disconnect from panel.

        Always releases the active-connection registration and clears state,
        even when the transport has already dropped, so a later ``connect()``
        can succeed.
        """
        # Nothing to release and nothing to tear down.
        if self._connection is None and self._active_key is None:
            return

        _LOGGER.info("Disconnecting from panel")
        # Stop keep-alive loop if running
        await self.stop_keepalive()
        # Send panel disconnect command only if the link is still up.
        try:
            if self.is_connected and self._connection and self._protocol:
                _LOGGER.debug("Sending panel disconnect command")
                disc = self._protocol.encode_command(DMPCommand.DISCONNECT.value)
                await self._connection.send_and_receive(disc)
        except Exception as e:
            _LOGGER.debug("Panel disconnect send failed: %s", e)

        # Cleanup active connection guard (must happen even after a drop).
        if self._active_key is not None:
            _ACTIVE_CONNECTIONS.discard(self._active_key)
            self._active_key = None
```

### PYDMP-011 — status_parser never maps Door-Access (`Zj`) / Service-Code (`Zm`) events

`status_parser.py:103-131` — both fall into the `else` branch which only tries
    `DMPQualifierEvent`, so `code_enum` comes back `None` even though `DMPAccessEvent` /
    `DMPServiceUserEvent` exist and are exported. Same fall-through gap for zone categories
    `Zb/Zf/Zi/Zp/Zd/Zh/Zk`.

**Impacted code**

src/pydmp/status_parser.py:98-131 (category dispatch — no branch for `DOOR_ACCESS`/`SERVICE_CODE`)
```python
    # Map type_code into a specific enum when applicable
    code_enum: object | None = None
    if category is not None and msg.type_code:
        code = msg.type_code
        try:
            if category is DMPEventType.ARMING_STATUS:
                code_enum = DMPArmingEvent(code)
            elif category is DMPEventType.REAL_TIME_STATUS:
                code_enum = DMPRealTimeStatusEvent(code)
            elif category in (
                DMPEventType.ZONE_ALARM,
                DMPEventType.ZONE_RESTORE,
                DMPEventType.ZONE_TROUBLE,
                DMPEventType.ZONE_FAULT,
                DMPEventType.ZONE_BYPASS,
                DMPEventType.ZONE_RESET,
            ):
                code_enum = DMPZoneEvent(code)
            elif category is DMPEventType.USER_CODES:
                code_enum = DMPUserCodeEvent(code)
            elif category is DMPEventType.SCHEDULES:
                code_enum = DMPScheduleEvent(code)
            elif category is DMPEventType.HOLIDAYS:
                code_enum = DMPHolidayEvent(code)
            elif category is DMPEventType.EQUIPMENT:
                code_enum = DMPEquipmentEvent(code)
            else:
                # Qualifiers sometimes ride along in other frames
                try:
                    code_enum = DMPQualifierEvent(code)
                except ValueError:
                    code_enum = None
        except ValueError:
            code_enum = None
```

src/pydmp/const/events.py:29,32 (`DOOR_ACCESS`/`SERVICE_CODE` categories exist but have no dispatch branch above)
```python
    DOOR_ACCESS = "Zj"
```
```python
    SERVICE_CODE = "Zm"
```

src/pydmp/const/events.py:156-165, 198-200 (`DMPAccessEvent`/`DMPServiceUserEvent` exist and are unused by the dispatch)
```python
class DMPAccessEvent(StrEnum):
    ACCESS_GRANTED = "DA"
    DENIED_ARMED = "AA"
    DENIED_INVALID_AREA = "IA"
    DENIED_INVALID_TIME = "IT"
    DENIED_PREVIOUS = "AP"
    DENIED_INVALID_CODE = "IC"
    DENIED_INVALID_LEVEL = "IL"
    DENIED_WRONG_PIN = "WP"
    DENIED_INACTIVE_USER = "IN"
```
```python
class DMPServiceUserEvent(StrEnum):
    START = "ST"
    STOP = "SP"
```

### PYDMP-012 — Sync API parity gap

`panel_sync.py` wraps none of: `arm_areas`, `disarm_areas`,
    `update_output_status`, `sensor_reset`, `get_user_codes`, `get_user_profiles`, `check_code`,
    keepalive, `attach_status_server`. `AreaSync.arm_sync` (`area.py:212-214`) also drops the
    `instant` flag the async version supports.

**Impacted code**

src/pydmp/panel_sync.py:54-154 (`DMPPanelSync`'s complete public surface — only connection lifecycle
and entity getters are forwarded; no arm/disarm/output/user/keepalive/status-server methods)
```python
    def connect(self, host: str, account: str, remote_key: str) -> None:
        ...
    def disconnect(self) -> None:
        ...
    def update_status(self) -> None:
        ...
    def get_areas(self) -> list[AreaSync]:
        ...
    def get_area(self, number: int) -> AreaSync:
        ...
    def get_zones(self) -> list[ZoneSync]:
        ...
    def get_zone(self, number: int) -> ZoneSync:
        ...
    def get_outputs(self) -> list[OutputSync]:
        ...
    def get_output(self, number: int) -> OutputSync:
        ...

    # Emergency trigger helpers were previously wired to non-existent async methods.
    # If needed in the future, map to configured output pulses instead.

    def _wrap_area(self, area: Area) -> AreaSync:
        ...
```

src/pydmp/area.py:212-214 (`AreaSync.arm_sync` drops the `instant` flag)
```python
    def arm_sync(self, bypass_faulted: bool = False, force_arm: bool = False) -> None:
        """Arm area (sync)."""
        self._panel_sync._run(self._area.arm(bypass_faulted, force_arm))
```

### PYDMP-025 — Trailing-comma discrepancy: `commands.md` conflicts with `dmp.lua`, pydmp matches the driver

**Likely CLOSE — downgraded after `dmp.lua` validation.** `commands.md` (XR500 Simpl+ doc)
marks the trailing comma as required on disarm (`!O01,\r`) and restore (`!Y023,\r`). But the
deployed Control4 driver `dmp.lua` sends **no comma** — `self.Send("!O"..area)` (dmp.lua:2091,
also `!O00` / `!O010203`) and `self.Send("!Y"..zone)` (dmp.lua:2067) — exactly matching what
pydmp emits (`!O01`, `!Y001`) and what `test_command_lengths.py` pins. So the two references
disagree, and the one that matches a *working deployed driver* is the comma-less form pydmp
already uses. This is a documentation conflict, not a pydmp defect. Recommendation: keep pydmp
as-is; treat as a hardware-verify footnote only (confirm the panel accepts the comma-less form,
which the driver's field history strongly implies), and note the `commands.md` discrepancy.

**Impacted code**

dmp.lua:2088-2093 (disarm — no comma) / dmp.lua:2066-2068 (restore — no comma):
```lua
    function self.DisarmSystem(aNum)
        if(aNum) then
            self.Send("!O"..string.format("%02d",aNum))   -- e.g. "!O01", no comma
        else
            self.Send("!O00")
        end
    end
    function self.ResetByPassZone(zNum)
        self.Send("!Y"..string.format("%03d",zNum))        -- e.g. "!Y023", no comma
    end
```

commands.md (Disarm Area / Reset Zone) — the outlier that claims a comma:
```
!O<AreaNumber>,\r    // Comma is required even with no parameters.
!Y<ZoneNumber>,\r    // Comma required.
```

### PYDMP-026 — Arm command has a spurious third flag; the 2nd flag is likely `instant`, not `force`

**Re-scoped — this is a live wire-format bug, not just an unverified extension.** The DMP `!C`
arm command takes **two** flags: `!C<area>,<flag1><flag2>`. Both references agree on the
two-flag structure — `dmp.lua` (dmp.lua:2072/2085) and `commands.md`. pydmp instead sends a
**third** flag: `ARM = "!C{area},{bypass}{force}{instant}"`, so `arm_areas(instant=True)` emits
`!C01,NNY` — a three-character flag field neither reference supports and the panel may NAK.

**Working hypothesis (owner, domain knowledge): the 2nd flag position *is* `instant`, not
`force`.** The DMP arm command is commonly `!C[area],[bypass][instant]`. `dmp.lua` labels its
second flag `FORCEBADZONES` (via the `AutoForceArmBadZones` property, dmp.lua:3013-3016), but
that is likely the Control4 driver author's mislabel — the driver handles instant/no-entry-delay
through a *separate* `EntryAndExitDelay` config (dmp.lua:3017), never through a `!C` flag, which
is exactly what you'd expect if the 2nd `!C` flag already were "instant." If so, pydmp's model is
wrong twice over: the third flag is spurious, and what it calls `force_arm` (2nd position) is
really the instant/no-delay control.

**Live impact:** hass-dmp already calls `arm_areas([...], instant=True)` for arm-night
(`hass-dmp/custom_components/dmp/alarm_control_panel.py:131`), so this malformed three-flag
command is being sent in production today.

**Proposed fix (needs hardware confirmation of flag semantics + an API decision):** collapse to
two flags — `ARM = "!C{area},{bypass}{instant}"` — and map the public `instant=` kwarg to the
2nd position. Keep the `instant=` keyword (hass-dmp depends on it); decide what to do with the
now-redundant `force_arm` param (deprecate, or keep as an alias for the same flag). Verify the
actual 2nd-flag meaning against a real panel before committing, since the only label evidence
(`dmp.lua`) says "force."

**Impacted code**

src/pydmp/const/commands.py:36
```python
    ARM = "!C{area},{bypass}{force}{instant}"   # third flag unsupported by either reference
```

src/pydmp/panel.py:600-609 (defaults send `!C..,NNY` for instant; `force` occupies the 2nd flag)
```python
        bypass = "Y" if bypass_faulted else "N"
        force = "Y" if force_arm else "N"
        instant_flag = "Y" if instant is True else ("N" if instant is False else "")
        resp = await self._send_command(
            DMPCommand.ARM.value, area=areas_concat,
            bypass=bypass, force=force, instant=instant_flag,
        )
```

dmp.lua:2069-2075 (two flags; 2nd labeled FORCEBADZONES — suspected mislabel of "instant"):
```lua
    function self.ArmSystem(aNum)
        if(aNum) then
            self.Send("!C"..string.format("%02d",aNum)..","..self.BYPASSBADZONES..self.FORCEBADZONES)
        else
            self.Send("!C00,"..self.BYPASSBADZONES..self.FORCEBADZONES)
        end
    end
```

## Security (S3 listener + input handling)

### PYDMP-013 — S3 listener is unauthenticated with unbounded buffering

`status_server.py:68-147`
    Accepts any peer, never validates source/account, no connection limit, and `buf += chunk` grows
    without bound if no `\r` arrives (memory DoS). A forged `Zu` event reaches
    `panel.py:494-498` and triggers a full user-code fetch/decrypt. Mitigated today only by the
    loopback bind default; the trust assumption is undocumented and CLI `listen --host` permits
    routable binds. Add a max-buffer cap, and document/validate the account.

**Impacted code**

src/pydmp/status_server.py:68-84 (`_handle_client` — no peer validation, unbounded `buf`)
```python
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        _LOGGER.info("S3 status connection from %s", peer)
        buf = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buf += chunk
                _LOGGER.debug("[s3] recv chunk %d bytes", len(chunk))
                # Process complete frames terminated by CR (\r)
                while b"\r" in buf:
                    line, buf = buf.split(b"\r", 1)
                    if not line:
                        continue
                    await self._process_line(line, writer)
```

src/pydmp/panel.py:484-502 (`attach_status_server` — any `Zu` event triggers `_refresh_user_cache`)
```python
    def attach_status_server(self, server: Any) -> None:
        """Attach a DMPStatusServer to auto-refresh user cache on Zu events.

        When the server receives a User Codes (Zu) event, the panel will refresh
        its user cache in the background. Call detach_status_server to remove.
        """

        if server in self._status_callbacks:
            return

        async def _on_event(msg: Any) -> None:
            try:
                evt = parse_s3_message(msg)
                if evt.category is DMPEventType.USER_CODES:
                    await self._refresh_user_cache()
            except Exception as e:
                _LOGGER.debug("Status server callback error: %s", e)

        self._status_callbacks[server] = _on_event
```

### PYDMP-014 — No `\r` sanitization on values framed into commands

`protocol.py:129-137`
    `command.format(**kwargs)` + `\r` terminator with no control-char check; a `remote_key`
    containing `\r` smuggles a second command in one write. Operator-supplied today, so low
    exploitability, but validation ("account = 5 digits" etc.) should be enforced at the boundary.

**Impacted code**

src/pydmp/protocol.py:129-137
```python
        try:
            # Format command with parameters
            formatted_command = command.format(**kwargs)

            # Build full message: @[ACCOUNT][COMMAND]\r
            message = f"{MESSAGE_PREFIX}{self.account_number}{formatted_command}{MESSAGE_TERMINATOR}"

            _LOGGER.debug("Encoded command: %s", message.strip())
            return message.encode()
```

### PYDMP-024 — Auth response echoes the remote key into inbound debug logs

**New (from `commands.md` comparison).** The documented login response is `+V2<RemoteKey>`
(success) / `-V2<RemoteKey>` (failure) — the panel echoes the credential back. The PYDMP-002
fix redacts `!V2<key>` on the *outbound* debug logs, but the transport's inbound chunk logging
(`_receive()`, the `"<<< chunk ..."` debug lines in transport.py:113-120) prints raw received
bytes verbatim, so the echoed key would land in DEBUG logs on every authentication. Fix:
apply the same `V2`-anchored redaction to the inbound debug path (and confirm on real
hardware whether the TCP variant actually echoes the key).

**Impacted code**

src/pydmp/transport.py:113-120 (inbound bytes logged unredacted; full `_receive` quoted under
PYDMP-005)
```python
                    try:
                        _LOGGER.debug(
                            "<<< chunk %d bytes: %r",
                            len(chunk),
                            chunk.decode("utf-8", errors="replace"),
                        )
                    except Exception:
                        _LOGGER.debug("<<< chunk %d bytes: %r", len(chunk), chunk)
```

commands.md (Login):
```
Response:
- +V2<RemoteKey> on success
- -V2<RemoteKey> on failure
```

## Quality / dead code

### PYDMP-020 — Dead legacy `DMPEvent` enum (~60 lines)

const/events.py:45-107; exported, referenced
    nowhere, duplicates the category enums.

**Impacted code**

src/pydmp/const/events.py:45-63 (start of the dead legacy enum; full class spans 45-107)
```python
class DMPEvent(StrEnum):
    """Common event type codes (legacy/unscoped).

    Prefer the category-specific enums below for full coverage and to avoid
    ambiguity where the same code is reused across categories.
    """

    # Zone types
    BLANK = "BL"
    FIRE = "FI"
    BURGLARY = "BU"
    SUPERVISORY = "SV"
    PANIC = "PN"
    EMERGENCY = "EM"
    AUXILIARY_1 = "A1"
    AUXILIARY_2 = "A2"
    CARBON_MONOXIDE = "CO"
    VIDEO_ALARM = "VA"
```

src/pydmp/const/events.py:102-107 (end of the same class)
```python
    # Service / Qualifiers (subset)
    SERVICE_START = "ST"
    SERVICE_STOP = "SP"
    SERVICE = "DT"
    ALL_AREAS_ARMED = "AC"
    LOCAL_ALARM_OR_RESTORE = "LC"
```

