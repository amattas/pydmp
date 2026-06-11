---
title: API Reference
mdx:
  format: md
---

<a id="pydmp"></a>

# pydmp

PyDMP - Python library for controlling DMP alarm systems.

Platform-agnostic library for interfacing with DMP (Digital Monitoring Products)
alarm panels via TCP/IP.

Example (Async):
    >>> import asyncio
    >>> from pydmp import DMPPanel
    >>>
    >>> async def main():
    ...     panel = DMPPanel()
    ...     await panel.connect("192.168.1.100", "00001", "YOUR_KEY")
    ...     areas = await panel.get_areas()
    ...     await areas[0].arm()
    ...     await panel.disconnect()
    >>>
    >>> asyncio.run(main())

Example (Sync):
    >>> from pydmp import DMPPanelSync
    >>>
    >>> panel = DMPPanelSync()
    >>> panel.connect("192.168.1.100", "00001", "YOUR_KEY")
    >>> areas = panel.get_areas()
    >>> areas[0].arm_sync()
    >>> panel.disconnect()

<a id="pydmp.user"></a>

# pydmp.user

<a id="pydmp.user.UserCode"></a>

## UserCode Objects

```python
@dataclass
class UserCode()
```

Decrypted user code record.

<a id="pydmp.panel_sync"></a>

# pydmp.panel\_sync

High-level synchronous panel controller.

<a id="pydmp.panel_sync.DMPPanelSync"></a>

## DMPPanelSync Objects

```python
class DMPPanelSync()
```

High-level synchronous interface to DMP panel.

<a id="pydmp.panel_sync.DMPPanelSync.__init__"></a>

#### \_\_init\_\_

```python
def __init__(port: int = DEFAULT_PORT, timeout: float = 10.0)
```

Initialize sync panel.

**Arguments**:

- `port` - TCP port (default: 2011)
- `timeout` - Connection timeout in seconds

<a id="pydmp.panel_sync.DMPPanelSync.is_connected"></a>

#### is\_connected

```python
@property
def is_connected() -> bool
```

Check if connected to panel.

<a id="pydmp.panel_sync.DMPPanelSync.connect"></a>

#### connect

```python
def connect(host: str, account: str, remote_key: str) -> None
```

Connect to panel and authenticate.

**Arguments**:

- `host` - Panel IP address or hostname
- `account` - 5-digit account number
- `remote_key` - Remote key for authentication

<a id="pydmp.panel_sync.DMPPanelSync.disconnect"></a>

#### disconnect

```python
def disconnect() -> None
```

Disconnect from panel.

<a id="pydmp.panel_sync.DMPPanelSync.update_status"></a>

#### update\_status

```python
def update_status() -> None
```

Update status of all areas and zones from panel.

<a id="pydmp.panel_sync.DMPPanelSync.get_areas"></a>

#### get\_areas

```python
def get_areas() -> list[AreaSync]
```

Get all areas.

**Returns**:

  List of AreaSync objects

<a id="pydmp.panel_sync.DMPPanelSync.get_area"></a>

#### get\_area

```python
def get_area(number: int) -> AreaSync
```

Get specific area by number.

**Arguments**:

- `number` - Area number (1-8)
  

**Returns**:

  AreaSync object

<a id="pydmp.panel_sync.DMPPanelSync.get_zones"></a>

#### get\_zones

```python
def get_zones() -> list[ZoneSync]
```

Get all zones.

**Returns**:

  List of ZoneSync objects

<a id="pydmp.panel_sync.DMPPanelSync.get_zone"></a>

#### get\_zone

```python
def get_zone(number: int) -> ZoneSync
```

Get specific zone by number.

**Arguments**:

- `number` - Zone number (1-999)
  

**Returns**:

  ZoneSync object

<a id="pydmp.panel_sync.DMPPanelSync.get_outputs"></a>

#### get\_outputs

```python
def get_outputs() -> list[OutputSync]
```

Get all outputs.

**Returns**:

  List of OutputSync objects

<a id="pydmp.panel_sync.DMPPanelSync.get_output"></a>

#### get\_output

```python
def get_output(number: int) -> OutputSync
```

Get specific output by number.

**Arguments**:

- `number` - Output number (1-4)
  

**Returns**:

  OutputSync object

<a id="pydmp.panel_sync.DMPPanelSync.__enter__"></a>

#### \_\_enter\_\_

```python
def __enter__() -> "DMPPanelSync"
```

Context manager entry.

<a id="pydmp.panel_sync.DMPPanelSync.__exit__"></a>

#### \_\_exit\_\_

```python
def __exit__(*args: Any) -> None
```

Context manager exit.

<a id="pydmp.panel_sync.DMPPanelSync.__repr__"></a>

#### \_\_repr\_\_

```python
def __repr__() -> str
```

String representation.

<a id="pydmp.transport"></a>

# pydmp.transport

Async TCP transport to DMP panel (raw bytes I/O only).

<a id="pydmp.transport.DMPTransport"></a>

## DMPTransport Objects

```python
class DMPTransport()
```

Async TCP transport to DMP panel.

This class is responsible only for socket lifecycle, rate limiting, and
sending/receiving raw bytes. No protocol encoding/decoding occurs here.

<a id="pydmp.transport.DMPTransport.connect"></a>

#### connect

```python
async def connect() -> None
```

Establish TCP connection.

<a id="pydmp.transport.DMPTransport.disconnect"></a>

#### disconnect

```python
async def disconnect() -> None
```

Close TCP connection.

<a id="pydmp.transport.DMPTransport.send_and_receive"></a>

#### send\_and\_receive

```python
async def send_and_receive(data: bytes) -> bytes
```

Send raw bytes and return accumulated response bytes.

<a id="pydmp.protocol"></a>

# pydmp.protocol

DMP protocol encoder and decoder.

<a id="pydmp.protocol.AreaStatus"></a>

## AreaStatus Objects

```python
@dataclass
class AreaStatus()
```

Area status from panel.

<a id="pydmp.protocol.ZoneStatus"></a>

## ZoneStatus Objects

```python
@dataclass
class ZoneStatus()
```

Zone status from panel.

<a id="pydmp.protocol.StatusResponse"></a>

## StatusResponse Objects

```python
@dataclass
class StatusResponse()
```

Combined status response from panel.

<a id="pydmp.protocol.OutputStatus"></a>

## OutputStatus Objects

```python
@dataclass
class OutputStatus()
```

Output status from panel (*WQ).

<a id="pydmp.protocol.DMPProtocol"></a>

## DMPProtocol Objects

```python
class DMPProtocol()
```

DMP protocol encoder/decoder.

<a id="pydmp.protocol.DMPProtocol.__init__"></a>

#### \_\_init\_\_

```python
def __init__(account_number: str, remote_key: str = "")
```

Initialize protocol handler.

**Arguments**:

- `account_number` - 5-digit account number (left-padded with spaces or zeros)
- `remote_key` - Remote key for authentication

<a id="pydmp.protocol.DMPProtocol.encode_command"></a>

#### encode\_command

```python
def encode_command(command: str, **kwargs: Any, ,) -> bytes
```

Encode a command for transmission to panel.

**Arguments**:

- `command` - Command template (e.g., "!C{area},{bypass}{force}")
- `**kwargs` - Parameters to substitute into command template
  

**Returns**:

  Encoded command as bytes
  

**Raises**:

- `DMPProtocolError` - If command cannot be encoded

<a id="pydmp.protocol.DMPProtocol.decode_response"></a>

#### decode\_response

```python
def decode_response(response: bytes) -> str | StatusResponse | UserCodesResponse | UserProfilesResponse | OutputsResponse | None
```

Decode response from panel.

**Arguments**:

- `response` - Raw bytes from panel
  

**Returns**:

  - ACK/NAK string for command acknowledgments
  - StatusResponse for status queries
  - None for empty/auth responses
  

**Raises**:

- `DMPInvalidResponseError` - If response cannot be decoded

<a id="pydmp.profile"></a>

# pydmp.profile

<a id="pydmp.profile.UserProfile"></a>

## UserProfile Objects

```python
@dataclass
class UserProfile()
```

User profile record (not encrypted).

<a id="pydmp.status_server"></a>

# pydmp.status\_server

Async Serial 3 (S3) realtime status server for DMP panels.

This server listens for Serial 3 (Z-frames) pushed by the panel and
invokes registered callbacks with parsed messages.

**Notes**:

  - Configure your DMP panel to connect to this machine/port for realtime
  S3 status (Z-frames). Only one connection is expected.
  - The server sends an ACK per message: STX + [5-byte account] + 0x06 + CR.

<a id="pydmp.status_server.S3Message"></a>

## S3Message Objects

```python
@dataclass
class S3Message()
```

Parsed Serial 3 Z-frame.

<a id="pydmp.status_server.DMPStatusServer"></a>

## DMPStatusServer Objects

```python
class DMPStatusServer()
```

Async TCP server for DMP Serial 3 realtime status (Z-frames).

<a id="pydmp.transport_sync"></a>

# pydmp.transport\_sync

Synchronous wrapper for DMP transport + protocol (bytes + codec).

<a id="pydmp.transport_sync.DMPTransportSync"></a>

## DMPTransportSync Objects

```python
class DMPTransportSync()
```

Synchronous wrapper combining DMPTransport and DMPProtocol.

<a id="pydmp.transport_sync.DMPTransportSync.__init__"></a>

#### \_\_init\_\_

```python
def __init__(host: str, account: str, remote_key: str, port: int = DEFAULT_PORT, timeout: float = 10.0)
```

Initialize sync transport.

<a id="pydmp.transport_sync.DMPTransportSync.connect"></a>

#### connect

```python
def connect() -> None
```

Establish connection and authenticate.

<a id="pydmp.transport_sync.DMPTransportSync.disconnect"></a>

#### disconnect

```python
def disconnect() -> None
```

Disconnect gracefully.

<a id="pydmp.transport_sync.DMPTransportSync.send_command"></a>

#### send\_command

```python
def send_command(command: str, encrypt_user_code: bool = False, user_code: str | None = None, **kwargs: Any, ,) -> str | StatusResponse | None
```

Send a protocol command and return decoded response.

<a id="pydmp.const"></a>

# pydmp.const

Constants for DMP protocol.

<a id="pydmp.const.responses"></a>

# pydmp.const.responses

DMP protocol response prefixes and status text maps.

Includes:
- Command acknowledgments ("+"/"-")
- Convenience text mapping for common status characters seen in status replies
  (mirrors the mapping used by hass-dmp's StatusResponse).

<a id="pydmp.const.responses.DMPResponse"></a>

## DMPResponse Objects

```python
class DMPResponse(str,  Enum)
```

DMP panel response message prefixes.

<a id="pydmp.const.events"></a>

# pydmp.const.events

DMP event types and codes.

Derived from DMP LT-1959 "SCS‑VR Reference Guide: Panel Messages".
This file defines:
- Event categories (Zx "Event Definition" field)
- Event type codes (tXX "Event Type" field), grouped by category

Note: Some codes (e.g., AD, IN, PR) are reused across categories by the
protocol. To avoid ambiguity in Python Enums, category-specific enums are
provided below. The legacy DMPEvent enum remains for common codes but is
not exhaustive. Prefer category enums for precise handling.

<a id="pydmp.const.events.DMPEventType"></a>

## DMPEventType Objects

```python
class DMPEventType(str,  Enum)
```

Event Definition categories (Zx).

<a id="pydmp.const.events.DMPEvent"></a>

## DMPEvent Objects

```python
class DMPEvent(str,  Enum)
```

Common event type codes (legacy/unscoped).

Prefer the category-specific enums below for full coverage and to avoid
ambiguity where the same code is reused across categories.

<a id="pydmp.const.protocol"></a>

# pydmp.const.protocol

Protocol-level constants for the DMP transport and framing.

<a id="pydmp.const.commands"></a>

# pydmp.const.commands

DMP protocol commands.

<a id="pydmp.const.commands.DMPCommand"></a>

## DMPCommand Objects

```python
class DMPCommand(str,  Enum)
```

DMP panel commands.

<a id="pydmp.const.strings"></a>

# pydmp.const.strings

Human‑readable strings for statuses and system messages.

This module centralizes user‑facing strings to make future
internationalization (i18n) straightforward. By default, it
exposes English strings. A future enhancement could expose
per‑locale mappings and a simple selection mechanism.

<a id="pydmp.crypto"></a>

# pydmp.crypto

LFSR-based encryption for DMP user codes.

DMP uses a Linear Feedback Shift Register (LFSR) algorithm for encrypting
user codes in certain commands. The algorithm is symmetric (encrypt = decrypt).

<a id="pydmp.crypto.DMPCrypto"></a>

## DMPCrypto Objects

```python
class DMPCrypto()
```

LFSR encryption for DMP user codes.

<a id="pydmp.crypto.DMPCrypto.__init__"></a>

#### \_\_init\_\_

```python
def __init__(account_number: int, remote_key: str = "")
```

Initialize crypto with account number and optional remote key.

**Arguments**:

- `account_number` - 5-digit account number (1-99999)
- `remote_key` - Remote key for authentication (not used for Entree connections)

<a id="pydmp.crypto.DMPCrypto.encrypt_string"></a>

#### encrypt\_string

```python
def encrypt_string(string_to_encrypt: str) -> str
```

Encrypt a string using LFSR algorithm.

The control string determines which positions are encrypted:
- '-': Skip (no encryption)
- '2': Encrypt 2-char hex value
- '3': Encrypt 3-digit decimal value

**Arguments**:

- `string_to_encrypt` - String to encrypt (typically user code + data)
  

**Returns**:

  Encrypted string

<a id="pydmp.crypto.DMPCrypto.decrypt_string"></a>

#### decrypt\_string

```python
def decrypt_string(string_to_decrypt: str) -> str
```

Decrypt a string using LFSR algorithm.

Since LFSR XOR is symmetric, decryption is identical to encryption.

**Arguments**:

- `string_to_decrypt` - String to decrypt
  

**Returns**:

  Decrypted string

<a id="pydmp.crypto.DMPCrypto.encrypt_user_code"></a>

#### encrypt\_user\_code

```python
def encrypt_user_code(user_code: str) -> str
```

Encrypt a user code for use in disarm commands.

**Arguments**:

- `user_code` - 4-6 digit user code
  

**Returns**:

  Encrypted user code

<a id="pydmp.cli"></a>

# pydmp.cli

Command-line interface for PyDMP.

<a id="pydmp.cli.SectionedGroup"></a>

## SectionedGroup Objects

```python
class SectionedGroup(click.Group)
```

Click Group that renders commands in named sections for --help.

<a id="pydmp.cli.load_config"></a>

#### load\_config

```python
def load_config(config_path: Path) -> dict
```

Load configuration from YAML file.

**Arguments**:

- `config_path` - Path to config file
  

**Returns**:

  Configuration dictionary

<a id="pydmp.cli.cli"></a>

#### cli

```python
@click.group(
    cls=SectionedGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
    sections=[
        ("Panel Control", ["arm", "disarm", "sensor-reset"]),
        (
            "Status & Query",
            ["get-areas", "get-zones", "get-outputs", "get-users", "get-profiles", "check-code"],
        ),
        ("Zones", ["set-zone-bypass", "set-zone-restore"]),
        ("Outputs", ["output", "set-output"]),
        ("Realtime", ["listen"]),
    ],
)
@click.version_option(__version__, "-v", "--version")
@click.option(
    "--config",
    "-c",
    # Do not require the file to exist so commands like 'listen'
    # can run without a config present (tests/CI environments).
    type=click.Path(path_type=Path),
    default="config.yaml",
    help="Configuration file path",
)
@click.option("--quiet", "-q", is_flag=True, help="Reduce output (WARNING)")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging (overrides other flags)")
@click.pass_context
def cli(ctx: click.Context, config: Path, quiet: bool, debug: bool) -> None
```

PyDMP - Control DMP alarm panels from command line.

<a id="pydmp.cli.arm_cmd"></a>

#### arm\_cmd

```python
@cli.command("arm", context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("areas", type=str)
@click.option("--bypass-faulted", "-b", is_flag=True, help="Bypass faulted zones")
@click.option("--force-arm", "-f", is_flag=True, help="Force arm bad zones")
@click.option("-i", "--instant/--no-instant", default=None, help="Remove entry/exit delays")
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def arm_cmd(ctx: click.Context, areas: str, bypass_faulted: bool, force_arm: bool, instant: bool | None, as_json: bool) -> None
```

Arm one or more areas, e.g. "1,2,3".

<a id="pydmp.cli.disarm"></a>

#### disarm

```python
@cli.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("area", type=int)
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def disarm(ctx: click.Context, area: int, as_json: bool) -> None
```

Disarm area.

<a id="pydmp.cli.set_zone_bypass"></a>

#### set\_zone\_bypass

```python
@cli.command("set-zone-bypass", context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("zone", type=int)
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def set_zone_bypass(ctx: click.Context, zone: int, as_json: bool) -> None
```

Bypass a zone.

<a id="pydmp.cli.set_zone_restore"></a>

#### set\_zone\_restore

```python
@cli.command("set-zone-restore", context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("zone", type=int)
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def set_zone_restore(ctx: click.Context, zone: int, as_json: bool) -> None
```

Restore (un-bypass) a zone.

<a id="pydmp.cli.output"></a>

#### output

```python
@cli.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("output", type=int)
@click.argument("action", type=click.Choice(["on", "off", "pulse", "toggle"]))
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def output(ctx: click.Context, output: int, action: str, as_json: bool) -> None
```

Control an output.

<a id="pydmp.cli.list_users"></a>

#### list\_users

```python
@cli.command("get-users", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def list_users(ctx: click.Context, as_json: bool) -> None
```

List panel user codes (decrypted).

<a id="pydmp.cli.list_profiles"></a>

#### list\_profiles

```python
@cli.command("get-profiles", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def list_profiles(ctx: click.Context, as_json: bool) -> None
```

List user profiles.

<a id="pydmp.cli.list_outputs"></a>

#### list\_outputs

```python
@cli.command("get-outputs", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def list_outputs(ctx: click.Context, as_json: bool) -> None
```

List outputs (1-4) and last-known state.

<a id="pydmp.cli.sensor_reset"></a>

#### sensor\_reset

```python
@cli.command("sensor-reset", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def sensor_reset(ctx: click.Context, as_json: bool) -> None
```

Send sensor reset (!E001).

<a id="pydmp.cli.check_code_cmd"></a>

#### check\_code\_cmd

```python
@cli.command("check-code", context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("code", type=str)
@click.option(
    "-p",
    "--include-pin/--no-include-pin",
    default=True,
    show_default=True,
    help="Match PIN as well as code",
)
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def check_code_cmd(ctx: click.Context, code: str, include_pin: bool, as_json: bool) -> None
```

Check if a code or PIN exists in the panel.

<a id="pydmp.cli.listen"></a>

#### listen

```python
@cli.command("listen", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--host", "-H", default="127.0.0.1", show_default=True, help="Listen host")
@click.option("--port", "-p", default=5001, show_default=True, type=int, help="Listen port")
@click.option("--duration", "-t", default=0, type=int, help="Seconds to run (0=until Ctrl+C)")
@click.option("--json", "-j", "as_json", is_flag=True, help="Output events as JSON (NDJSON)")
def listen(host: str, port: int, duration: int, as_json: bool) -> None
```

Run realtime S3 status server and print parsed events.

<a id="pydmp.cli.get_areas_cmd"></a>

#### get\_areas\_cmd

```python
@cli.command("get-areas", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def get_areas_cmd(ctx: click.Context, as_json: bool) -> None
```

List areas and their state.

<a id="pydmp.cli.get_zones_cmd"></a>

#### get\_zones\_cmd

```python
@cli.command("get-zones", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "-j", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def get_zones_cmd(ctx: click.Context, as_json: bool) -> None
```

List zones and their state.

<a id="pydmp.cli.set_output"></a>

#### set\_output

```python
@cli.command("set-output", context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("output", type=int)
@click.argument("action", type=click.Choice(["on", "off", "pulse", "toggle"]))
@click.pass_context
def set_output(ctx: click.Context, output: int, action: str) -> None
```

Control an output.

<a id="pydmp.cli.main"></a>

#### main

```python
def main() -> None
```

CLI entry point.

<a id="pydmp.zone"></a>

# pydmp.zone

Zone abstraction.

<a id="pydmp.zone.Zone"></a>

## Zone Objects

```python
class Zone()
```

Represents a DMP zone.

<a id="pydmp.zone.Zone.__init__"></a>

#### \_\_init\_\_

```python
def __init__(panel: "DMPPanel", number: int, name: str = "", state: str = "unknown")
```

Initialize zone.

**Arguments**:

- `panel` - Parent panel instance
- `number` - Zone number (1-999)
- `name` - Zone name
- `state` - Current zone state

<a id="pydmp.zone.Zone.state"></a>

#### state

```python
@property
def state() -> str
```

Get current state.

<a id="pydmp.zone.Zone.update_state"></a>

#### update\_state

```python
def update_state(state: str, name: str | None = None) -> None
```

Update zone state from status response.

**Arguments**:

- `state` - New state
- `name` - Updated name (optional)

<a id="pydmp.zone.Zone.is_open"></a>

#### is\_open

```python
@property
def is_open() -> bool
```

Check if zone is open/tripped.

<a id="pydmp.zone.Zone.is_normal"></a>

#### is\_normal

```python
@property
def is_normal() -> bool
```

Check if zone is normal (closed).

<a id="pydmp.zone.Zone.is_bypassed"></a>

#### is\_bypassed

```python
@property
def is_bypassed() -> bool
```

Check if zone is bypassed.

<a id="pydmp.zone.Zone.has_fault"></a>

#### has\_fault

```python
@property
def has_fault() -> bool
```

Check if zone has a fault.

<a id="pydmp.zone.Zone.formatted_number"></a>

#### formatted\_number

```python
@property
def formatted_number() -> str
```

Get zero-padded 3-digit zone number.

<a id="pydmp.zone.Zone.bypass"></a>

#### bypass

```python
async def bypass() -> None
```

Bypass this zone.

**Raises**:

- `DMPZoneError` - If bypass fails

<a id="pydmp.zone.Zone.restore"></a>

#### restore

```python
async def restore() -> None
```

Restore (un-bypass) this zone.

**Raises**:

- `DMPZoneError` - If restore fails

<a id="pydmp.zone.Zone.get_state"></a>

#### get\_state

```python
async def get_state() -> str
```

Get current state from panel.

**Returns**:

  Current zone state

<a id="pydmp.zone.Zone.__repr__"></a>

#### \_\_repr\_\_

```python
def __repr__() -> str
```

String representation.

<a id="pydmp.zone.Zone.to_dict"></a>

#### to\_dict

```python
def to_dict() -> dict
```

Return a JSON-serializable representation of the zone.

<a id="pydmp.zone.ZoneSync"></a>

## ZoneSync Objects

```python
class ZoneSync()
```

Synchronous wrapper for Zone.

<a id="pydmp.zone.ZoneSync.__init__"></a>

#### \_\_init\_\_

```python
def __init__(zone: Zone, panel_sync: "DMPPanelSync")
```

Initialize sync zone.

**Arguments**:

- `zone` - Async Zone instance
- `panel_sync` - Sync panel instance

<a id="pydmp.zone.ZoneSync.number"></a>

#### number

```python
@property
def number() -> int
```

Get zone number.

<a id="pydmp.zone.ZoneSync.name"></a>

#### name

```python
@property
def name() -> str
```

Get zone name.

<a id="pydmp.zone.ZoneSync.state"></a>

#### state

```python
@property
def state() -> str
```

Get current state.

<a id="pydmp.zone.ZoneSync.is_open"></a>

#### is\_open

```python
@property
def is_open() -> bool
```

Check if zone is open.

<a id="pydmp.zone.ZoneSync.is_normal"></a>

#### is\_normal

```python
@property
def is_normal() -> bool
```

Check if zone is normal.

<a id="pydmp.zone.ZoneSync.is_bypassed"></a>

#### is\_bypassed

```python
@property
def is_bypassed() -> bool
```

Check if zone is bypassed.

<a id="pydmp.zone.ZoneSync.has_fault"></a>

#### has\_fault

```python
@property
def has_fault() -> bool
```

Check if zone has fault.

<a id="pydmp.zone.ZoneSync.formatted_number"></a>

#### formatted\_number

```python
@property
def formatted_number() -> str
```

Get formatted number.

<a id="pydmp.zone.ZoneSync.bypass_sync"></a>

#### bypass\_sync

```python
def bypass_sync() -> None
```

Bypass zone (sync).

<a id="pydmp.zone.ZoneSync.restore_sync"></a>

#### restore\_sync

```python
def restore_sync() -> None
```

Restore zone (sync).

<a id="pydmp.zone.ZoneSync.get_state_sync"></a>

#### get\_state\_sync

```python
def get_state_sync() -> str
```

Get current state from panel (sync).

<a id="pydmp.zone.ZoneSync.__repr__"></a>

#### \_\_repr\_\_

```python
def __repr__() -> str
```

String representation.

<a id="pydmp.exceptions"></a>

# pydmp.exceptions

Exceptions for PyDMP.

<a id="pydmp.exceptions.DMPError"></a>

## DMPError Objects

```python
class DMPError(Exception)
```

Base exception for DMP errors.

<a id="pydmp.exceptions.DMPConnectionError"></a>

## DMPConnectionError Objects

```python
class DMPConnectionError(DMPError)
```

Connection-related errors.

<a id="pydmp.exceptions.DMPAuthenticationError"></a>

## DMPAuthenticationError Objects

```python
class DMPAuthenticationError(DMPConnectionError)
```

Authentication failed.

<a id="pydmp.exceptions.DMPTimeoutError"></a>

## DMPTimeoutError Objects

```python
class DMPTimeoutError(DMPConnectionError)
```

Operation timed out.

<a id="pydmp.exceptions.DMPProtocolError"></a>

## DMPProtocolError Objects

```python
class DMPProtocolError(DMPError)
```

Protocol-level errors.

<a id="pydmp.exceptions.DMPInvalidResponseError"></a>

## DMPInvalidResponseError Objects

```python
class DMPInvalidResponseError(DMPProtocolError)
```

Invalid or unexpected response from panel.

<a id="pydmp.exceptions.DMPCommandError"></a>

## DMPCommandError Objects

```python
class DMPCommandError(DMPError)
```

Command execution errors.

<a id="pydmp.exceptions.DMPCommandNAKError"></a>

## DMPCommandNAKError Objects

```python
class DMPCommandNAKError(DMPCommandError)
```

Command was rejected by panel (NAK response).

<a id="pydmp.exceptions.DMPInvalidParameterError"></a>

## DMPInvalidParameterError Objects

```python
class DMPInvalidParameterError(DMPError)
```

Invalid parameter provided.

<a id="pydmp.exceptions.DMPAreaError"></a>

## DMPAreaError Objects

```python
class DMPAreaError(DMPError)
```

Area-related errors.

<a id="pydmp.exceptions.DMPZoneError"></a>

## DMPZoneError Objects

```python
class DMPZoneError(DMPError)
```

Zone-related errors.

<a id="pydmp.exceptions.DMPOutputError"></a>

## DMPOutputError Objects

```python
class DMPOutputError(DMPError)
```

Output-related errors.

<a id="pydmp.panel"></a>

# pydmp.panel

High-level async panel controller.

<a id="pydmp.panel.DMPPanel"></a>

## DMPPanel Objects

```python
class DMPPanel()
```

High-level async interface to DMP panel.

<a id="pydmp.panel.DMPPanel.__init__"></a>

#### \_\_init\_\_

```python
def __init__(port: int = DEFAULT_PORT, timeout: float = 10.0)
```

Initialize panel.

**Arguments**:

- `port` - TCP port (default: 2011)
- `timeout` - Connection timeout in seconds

<a id="pydmp.panel.DMPPanel.is_connected"></a>

#### is\_connected

```python
@property
def is_connected() -> bool
```

Check if connected to panel.

<a id="pydmp.panel.DMPPanel.connect"></a>

#### connect

```python
async def connect(host: str, account: str, remote_key: str) -> None
```

Connect to panel and authenticate.

**Arguments**:

- `host` - Panel IP address or hostname
- `account` - 5-digit account number
- `remote_key` - Remote key for authentication
  

**Raises**:

- `DMPConnectionError` - If connection fails

<a id="pydmp.panel.DMPPanel.disconnect"></a>

#### disconnect

```python
async def disconnect() -> None
```

Disconnect from panel.

<a id="pydmp.panel.DMPPanel.update_status"></a>

#### update\_status

```python
async def update_status() -> None
```

Update status of all areas and zones from panel.

**Raises**:

- `DMPConnectionError` - If not connected or update fails

<a id="pydmp.panel.DMPPanel.get_areas"></a>

#### get\_areas

```python
async def get_areas() -> list[Area]
```

Get all areas.

**Returns**:

  List of Area objects
  

**Raises**:

- `DMPConnectionError` - If not connected

<a id="pydmp.panel.DMPPanel.get_area"></a>

#### get\_area

```python
async def get_area(number: int) -> Area
```

Get specific area by number.

**Arguments**:

- `number` - Area number (1-8)
  

**Returns**:

  Area object
  

**Raises**:

- `DMPConnectionError` - If not connected
- `KeyError` - If area not found

<a id="pydmp.panel.DMPPanel.get_zones"></a>

#### get\_zones

```python
async def get_zones() -> list[Zone]
```

Get all zones.

**Returns**:

  List of Zone objects
  

**Raises**:

- `DMPConnectionError` - If not connected

<a id="pydmp.panel.DMPPanel.get_zone"></a>

#### get\_zone

```python
async def get_zone(number: int) -> Zone
```

Get specific zone by number.

**Arguments**:

- `number` - Zone number (1-999)
  

**Returns**:

  Zone object
  

**Raises**:

- `DMPConnectionError` - If not connected
- `KeyError` - If zone not found

<a id="pydmp.panel.DMPPanel.get_outputs"></a>

#### get\_outputs

```python
async def get_outputs() -> list[Output]
```

Get all outputs.

Note: Outputs are created on-demand; prefer calling update_output_status()
first to populate real states from the panel.

**Returns**:

  List of Output objects

<a id="pydmp.panel.DMPPanel.get_output"></a>

#### get\_output

```python
async def get_output(number: int) -> Output
```

Get specific output by number.

**Arguments**:

- `number` - Output number (1-999)
  

**Returns**:

  Output object
  

**Raises**:

- `KeyError` - If output number invalid

<a id="pydmp.panel.DMPPanel.update_output_status"></a>

#### update\_output\_status

```python
async def update_output_status() -> None
```

Fetch output status from panel (*WQ) and update known outputs.

The panel returns a stream of output entries in frames. We request
the initial page for output 001, then continue with '?WQ' a few times
to collect subsequent chunks.

Note: Many residential installations only use outputs 1-4.

<a id="pydmp.panel.DMPPanel.sensor_reset"></a>

#### sensor\_reset

```python
async def sensor_reset() -> None
```

Send sensor reset command to the panel (!E001).

<a id="pydmp.panel.DMPPanel.get_user_codes"></a>

#### get\_user\_codes

```python
async def get_user_codes() -> list[UserCode]
```

Retrieve all user codes from the panel (decrypting entries).

<a id="pydmp.panel.DMPPanel.get_user_profiles"></a>

#### get\_user\_profiles

```python
async def get_user_profiles() -> list[UserProfile]
```

Retrieve all user profiles from the panel.

<a id="pydmp.panel.DMPPanel.check_code"></a>

#### check\_code

```python
async def check_code(code: str, *, include_pin: bool = True, refresh_if_missing: bool = True) -> UserCode | None
```

Check if a user code (or PIN) exists in the panel.

**Arguments**:

- `code` - The code/PIN string to validate
- `include_pin` - If True, also match against PIN codes
- `refresh_if_missing` - If True, refresh cache on miss and retry once
  

**Returns**:

  Matching UserCode or None if not found

<a id="pydmp.panel.DMPPanel.attach_status_server"></a>

#### attach\_status\_server

```python
def attach_status_server(server: Any) -> None
```

Attach a DMPStatusServer to auto-refresh user cache on Zu events.

When the server receives a User Codes (Zu) event, the panel will refresh
its user cache in the background. Call detach_status_server to remove.

<a id="pydmp.panel.DMPPanel.detach_status_server"></a>

#### detach\_status\_server

```python
def detach_status_server(server: Any) -> None
```

Detach a previously attached DMPStatusServer.

<a id="pydmp.panel.DMPPanel.start_keepalive"></a>

#### start\_keepalive

```python
async def start_keepalive(interval: float = 10.0) -> None
```

Start periodic keep-alive (!H) while connected.

**Arguments**:

- `interval` - Seconds between keep-alive messages (default: 10)

<a id="pydmp.panel.DMPPanel.stop_keepalive"></a>

#### stop\_keepalive

```python
async def stop_keepalive() -> None
```

Stop periodic keep-alive if running.

<a id="pydmp.panel.DMPPanel.arm_areas"></a>

#### arm\_areas

```python
async def arm_areas(area_numbers: list[int] | tuple[int, ...], bypass_faulted: bool = False, force_arm: bool = False, instant: bool | None = None) -> None
```

Arm one or more areas in a single command.

Concatenates two-digit area numbers per DMP format and sends
!C{areas},{bypass}{force}.

<a id="pydmp.panel.DMPPanel.disarm_areas"></a>

#### disarm\_areas

```python
async def disarm_areas(area_numbers: list[int] | tuple[int, ...]) -> None
```

Disarm one or more areas in a single command: !O{areas}.

<a id="pydmp.panel.DMPPanel.__aenter__"></a>

#### \_\_aenter\_\_

```python
async def __aenter__() -> "DMPPanel"
```

Async context manager entry.

<a id="pydmp.panel.DMPPanel.__aexit__"></a>

#### \_\_aexit\_\_

```python
async def __aexit__(*args: Any) -> None
```

Async context manager exit.

<a id="pydmp.panel.DMPPanel.__repr__"></a>

#### \_\_repr\_\_

```python
def __repr__() -> str
```

String representation.

<a id="pydmp.area"></a>

# pydmp.area

Area abstraction.

<a id="pydmp.area.Area"></a>

## Area Objects

```python
class Area()
```

Represents a DMP area.

<a id="pydmp.area.Area.__init__"></a>

#### \_\_init\_\_

```python
def __init__(panel: "DMPPanel", number: int, name: str = "", state: str = "unknown")
```

Initialize area.

**Arguments**:

- `panel` - Parent panel instance
- `number` - Area number (1-8)
- `name` - Area name
- `state` - Current area state

<a id="pydmp.area.Area.state"></a>

#### state

```python
@property
def state() -> str
```

Get current state.

<a id="pydmp.area.Area.update_state"></a>

#### update\_state

```python
def update_state(state: str, name: str | None = None) -> None
```

Update area state from status response.

**Arguments**:

- `state` - New state
- `name` - Updated name (optional)

<a id="pydmp.area.Area.is_armed"></a>

#### is\_armed

```python
@property
def is_armed() -> bool
```

Check if area is armed (any armed state).

<a id="pydmp.area.Area.is_disarmed"></a>

#### is\_disarmed

```python
@property
def is_disarmed() -> bool
```

Check if area is disarmed.

<a id="pydmp.area.Area.arm"></a>

#### arm

```python
async def arm(bypass_faulted: bool = False, force_arm: bool = False, instant: bool | None = None) -> None
```

Arm area.

**Arguments**:

- `bypass_faulted` - Bypass faulted zones (default: False)
- `force_arm` - Force arm bad zones (default: False)
- `instant` - Remove entry/exit delays (Y/N). If None, omit third flag.
  

**Raises**:

- `DMPAreaError` - If arm fails

<a id="pydmp.area.Area.disarm"></a>

#### disarm

```python
async def disarm() -> None
```

Disarm area.

Note: User code validation is typically done at the application level,
not sent to the panel in the protocol.

**Raises**:

- `DMPAreaError` - If disarm fails

<a id="pydmp.area.Area.get_state"></a>

#### get\_state

```python
async def get_state() -> str
```

Get current state from panel.

**Returns**:

  Current area state

<a id="pydmp.area.Area.__repr__"></a>

#### \_\_repr\_\_

```python
def __repr__() -> str
```

String representation.

<a id="pydmp.area.Area.to_dict"></a>

#### to\_dict

```python
def to_dict() -> dict
```

Return a JSON-serializable representation of the area.

<a id="pydmp.area.AreaSync"></a>

## AreaSync Objects

```python
class AreaSync()
```

Synchronous wrapper for Area.

<a id="pydmp.area.AreaSync.__init__"></a>

#### \_\_init\_\_

```python
def __init__(area: Area, panel_sync: "DMPPanelSync")
```

Initialize sync area.

**Arguments**:

- `area` - Async Area instance
- `panel_sync` - Sync panel instance

<a id="pydmp.area.AreaSync.number"></a>

#### number

```python
@property
def number() -> int
```

Get area number.

<a id="pydmp.area.AreaSync.name"></a>

#### name

```python
@property
def name() -> str
```

Get area name.

<a id="pydmp.area.AreaSync.state"></a>

#### state

```python
@property
def state() -> str
```

Get current state.

<a id="pydmp.area.AreaSync.is_armed"></a>

#### is\_armed

```python
@property
def is_armed() -> bool
```

Check if area is armed.

<a id="pydmp.area.AreaSync.is_disarmed"></a>

#### is\_disarmed

```python
@property
def is_disarmed() -> bool
```

Check if area is disarmed.

<a id="pydmp.area.AreaSync.arm_sync"></a>

#### arm\_sync

```python
def arm_sync(bypass_faulted: bool = False, force_arm: bool = False) -> None
```

Arm area (sync).

<a id="pydmp.area.AreaSync.disarm_sync"></a>

#### disarm\_sync

```python
def disarm_sync() -> None
```

Disarm area (sync).

<a id="pydmp.area.AreaSync.get_state_sync"></a>

#### get\_state\_sync

```python
def get_state_sync() -> str
```

Get current state from panel (sync).

<a id="pydmp.area.AreaSync.__repr__"></a>

#### \_\_repr\_\_

```python
def __repr__() -> str
```

String representation.

<a id="pydmp.output"></a>

# pydmp.output

Output abstraction.

<a id="pydmp.output.Output"></a>

## Output Objects

```python
class Output()
```

Represents a DMP output.

<a id="pydmp.output.Output.__init__"></a>

#### \_\_init\_\_

```python
def __init__(panel: "DMPPanel", number: int, name: str = "", state: str = "unknown")
```

Initialize output.

**Arguments**:

- `panel` - Parent panel instance
- `number` - Output number (1-4)
- `name` - Output name
- `state` - Current output state

<a id="pydmp.output.Output.state"></a>

#### state

```python
@property
def state() -> str
```

Get current state.

<a id="pydmp.output.Output.update_state"></a>

#### update\_state

```python
def update_state(state: str, name: str | None = None) -> None
```

Update output state.

**Arguments**:

- `state` - New state
- `name` - Updated name (optional)

<a id="pydmp.output.Output.is_on"></a>

#### is\_on

```python
@property
def is_on() -> bool
```

Check if output is on.

<a id="pydmp.output.Output.is_off"></a>

#### is\_off

```python
@property
def is_off() -> bool
```

Check if output is off.

<a id="pydmp.output.Output.formatted_number"></a>

#### formatted\_number

```python
@property
def formatted_number() -> str
```

Get zero-padded 3-digit output number.

<a id="pydmp.output.Output.set_mode"></a>

#### set\_mode

```python
async def set_mode(mode: str) -> None
```

Set output mode.

**Arguments**:

- `mode` - Output mode ('O'=Off, 'P'=Pulse, 'S'=Steady, 'M'=Momentary)
  

**Raises**:

- `DMPOutputError` - If command fails

<a id="pydmp.output.Output.turn_on"></a>

#### turn\_on

```python
async def turn_on() -> None
```

Turn output on (steady mode).

**Raises**:

- `DMPOutputError` - If command fails

<a id="pydmp.output.Output.turn_off"></a>

#### turn\_off

```python
async def turn_off() -> None
```

Turn output off.

**Raises**:

- `DMPOutputError` - If command fails

<a id="pydmp.output.Output.pulse"></a>

#### pulse

```python
async def pulse() -> None
```

Pulse output (momentary activation).

**Raises**:

- `DMPOutputError` - If command fails

<a id="pydmp.output.Output.toggle"></a>

#### toggle

```python
async def toggle() -> None
```

Toggle output state.

**Raises**:

- `DMPOutputError` - If command fails

<a id="pydmp.output.Output.__repr__"></a>

#### \_\_repr\_\_

```python
def __repr__() -> str
```

String representation.

<a id="pydmp.output.Output.to_dict"></a>

#### to\_dict

```python
def to_dict() -> dict
```

Return a JSON-serializable representation of the output.

<a id="pydmp.output.OutputSync"></a>

## OutputSync Objects

```python
class OutputSync()
```

Synchronous wrapper for Output.

<a id="pydmp.output.OutputSync.__init__"></a>

#### \_\_init\_\_

```python
def __init__(output: Output, panel_sync: "DMPPanelSync")
```

Initialize sync output.

**Arguments**:

- `output` - Async Output instance
- `panel_sync` - Sync panel instance

<a id="pydmp.output.OutputSync.number"></a>

#### number

```python
@property
def number() -> int
```

Get output number.

<a id="pydmp.output.OutputSync.name"></a>

#### name

```python
@property
def name() -> str
```

Get output name.

<a id="pydmp.output.OutputSync.state"></a>

#### state

```python
@property
def state() -> str
```

Get current state.

<a id="pydmp.output.OutputSync.is_on"></a>

#### is\_on

```python
@property
def is_on() -> bool
```

Check if output is on.

<a id="pydmp.output.OutputSync.is_off"></a>

#### is\_off

```python
@property
def is_off() -> bool
```

Check if output is off.

<a id="pydmp.output.OutputSync.turn_on_sync"></a>

#### turn\_on\_sync

```python
def turn_on_sync() -> None
```

Turn output on (sync).

<a id="pydmp.output.OutputSync.turn_off_sync"></a>

#### turn\_off\_sync

```python
def turn_off_sync() -> None
```

Turn output off (sync).

<a id="pydmp.output.OutputSync.pulse_sync"></a>

#### pulse\_sync

```python
def pulse_sync() -> None
```

Pulse output (sync).

<a id="pydmp.output.OutputSync.toggle_sync"></a>

#### toggle\_sync

```python
def toggle_sync() -> None
```

Toggle output (sync).

<a id="pydmp.output.OutputSync.__repr__"></a>

#### \_\_repr\_\_

```python
def __repr__() -> str
```

String representation.

<a id="pydmp.status_parser"></a>

# pydmp.status\_parser

Helper to convert Serial 3 (S3) messages into structured, typed events.

This module maps a low-level S3Message (from status_server) to enums and
fields from pydmp.const, making it easier to act on realtime events.

<a id="pydmp.status_parser.ParsedEvent"></a>

## ParsedEvent Objects

```python
@dataclass
class ParsedEvent()
```

Structured representation of a realtime SCS‑VR Z-message.

Fields may be None if not applicable for the message category.

<a id="pydmp.status_parser.parse_s3_message"></a>

#### parse\_s3\_message

```python
def parse_s3_message(msg: S3Message) -> ParsedEvent
```

Convert a Serial 3 (S3) message to a structured ParsedEvent with enums.

This function does not mutate any panel state; it only interprets the
incoming message. Use it inside your DMPStatusServer callbacks.

