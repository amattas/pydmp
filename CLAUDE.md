# PyDMP - Python Library for DMP Alarm Systems

## Project Overview

**Purpose**: Standalone, platform-agnostic Python library for controlling DMP (Digital Monitoring Products) alarm systems via TCP/IP.

**Features**:
- Low-level protocol communication with DMP panels
- High-level abstractions (panels, areas, zones, outputs)
- Both sync and async APIs with automatic rate limiting (0.3s)
- Full type hints and comprehensive error handling

### What This Is NOT
- Not a Home Assistant integration (though can be used to build one)
- Not tied to Control4 or any home automation platform
- Not a GUI application
- A standalone, reusable Python library
- Platform-independent and integration-friendly

## Quick Start

### Async API (Recommended)
```python
import asyncio
from pydmp import DMPPanel
from pydmp.const import AreaState, ZoneType

async def main():
    panel = DMPPanel()
    await panel.connect("192.168.1.100", "00001", "YOUR_KEY")

    # Arm/disarm area
    areas = await panel.get_areas()
    await areas[0].arm()

    # Check status
    state = await areas[0].get_state()
    if state == AreaState.ARMED_AWAY:
        print("Armed")

    # Check zones
    zones = await panel.get_zones()
    for zone in zones:
        if zone.zone_type == ZoneType.FIRE and zone.is_open:
            print(f"Fire alarm: Zone {zone.number}")

    await panel.disconnect()

asyncio.run(main())
```

### Sync API (Simple Scripts)
```python
from pydmp import DMPPanelSync
from pydmp.const import AreaState, ZoneState

panel = DMPPanelSync()
panel.connect("192.168.1.100", "00001", "YOUR_KEY")

areas = panel.get_areas()
areas[0].arm_sync()

state = areas[0].get_state_sync()
if state == AreaState.ARMED_AWAY:
    print("Armed")

panel.disconnect()
```

## Architecture Overview

```
pydmp/
├── src/pydmp/
│   ├── transport.py         # Async TCP transport (raw bytes I/O)
│   ├── transport_sync.py    # Sync wrapper (transport + protocol)
│   ├── protocol.py          # DMP protocol encoder/decoder
│   ├── crypto.py            # LFSR encryption for user codes
│   ├── panel.py             # Async panel controller
│   ├── panel_sync.py        # Sync panel controller
│   ├── status_server.py     # Serial 3 (S3) realtime listener
│   ├── status_parser.py     # Parse S3 Z-frames to typed events
│   ├── user.py              # User model
│   ├── profile.py           # Profile model
│   ├── area.py              # Area abstraction
│   ├── zone.py              # Zone abstraction
│   ├── output.py            # Output abstraction
│   ├── const/               # Constants (states, types, commands)
│   └── exceptions.py        # Exception hierarchy
├── src/pydmp/cli.py         # CLI tool
└── tests/                   # Unit & integration tests
```

**Core Classes** (see code docstrings for full API):
- `DMPTransport/DMPTransportSync`: TCP transport (async) and sync wrapper
- `DMPProtocol`: Message encoding/decoding
- `DMPCrypto`: LFSR encryption for user codes
- `DMPPanel/DMPPanelSync`: High-level panel control
- `DMPStatusServer`: Serial 3 (S3) realtime listener
- `Area`, `Zone`, `Output`: Entity abstractions

## DMP Protocol Essentials

### Connection
- **Protocol**: TCP/IP
- **Port**: 2011 (default)
- **Format**: `@[ACCOUNT][COMMAND]\r`
- **Account**: 5 digits, left-padded (e.g., `00001`)
- **Rate Limit**: 0.3s minimum between commands

### Encryption (LFSR)
User codes in arm/disarm commands are encrypted:
- Seed: `(account_number + user_code) & 0xFF`
- Control string: `"----2222222223333"` defines transformation
- Symmetric: encrypt = decrypt

### Core Commands

| Command | Description | Format | Encrypted |
|---------|-------------|--------|-----------|
| `!V2[KEY]` | Authenticate | `@[ACCT]!V2[KEY]\r` | No |
| `!V0` | Drop connection | `@[ACCT]!V0\r` | No |
| `!C` | Get config | `@[ACCT]!C\r` | No |
| `!S` | Get status | `@[ACCT]!S\r` | No |
| `?WB**Y001` | Get zone/area status | `@[ACCT]?WB**Y001\r` | No |
| `!O[A],[CODE]` | Disarm area | `@[ACCT]!O[A],[CODE]\r` | Yes |
| `!C[A],YN[I]` | Arm away | `@[ACCT]!C[A],YN[I]\r` | Partial |
| `!C[A],NN[I]` | Arm stay | `@[ACCT]!C[A],NN[I]\r` | Partial |
| `!X[ZZZ]` | Bypass zone | `@[ACCT]!X[ZZZ]\r` | No |
| `!Y[ZZZ]` | Restore zone | `@[ACCT]!Y[ZZZ]\r` | No |
| `!P[N]ON` | Output on | `@[ACCT]!P[N]ON\r` | No |
| `!P[N]OFF` | Output off | `@[ACCT]!P[N]OFF\r` | No |

Where: `[A]` = Area 1-8, `[ZZZ]` = Zone 001-999, `[N]` = Output 1-4, `[I]` = Instant flag

## ⚠️ CRITICAL: Complete DMP Protocol Implementation

**ESSENTIAL**: Implement ALL DMP panel commands from the Control4 Lua driver. Extract the **DMP protocol commands**, NOT Control4-specific code.

### Reference Implementation Guide

#### Using dmp.lua (Control4 Driver)

**Location**: `/Users/amattas/GitHub/pydmp/dmp.lua`

**EXTRACT DMP Commands From** (lines 803-935, 2211-2311, 4515-6105):
- `PARTITION_ARM/DISARM` → Extract `!C` and `!O` commands
- `BYPASS_ZONE` → Extract `!X` command
- `PGM_ON/OFF` → Extract `!P[N]ON/OFF` commands
- Encryption routine (lines 3773-3955) → LFSR implementation

**IGNORE Control4-Specific**:
- All `C4:*` functions
- `SendToProxy` calls
- XML proxy updates
- Properties handlers

**Key**: If it starts with `C4:` or mentions "Proxy", it's Control4-specific. Find the underlying DMP command inside.

**Terminology**: Control4 "Partitions" = DMP "Areas", Control4 "PGMs" = DMP "Outputs"

#### Using hass-dmp (Home Assistant)

**Location**: `/Users/amattas/GitHub/hass-dmp`

**EXTRACT**:
- `dmp_codes.py`: Command codes, response definitions
- `dmp_sender.py`: TCP implementation, message encoding
- Test files: Mock panel behavior, protocol examples

**IGNORE**: `async_setup_entry`, `config_flow`, `Entity` classes, HA-specific patterns

## Development Checklist

### Phase 1: Core Library
- [ ] TCP transport (`transport.py`, `transport_sync.py`)
- [ ] Protocol encoder/decoder (`protocol.py`)
- [ ] LFSR encryption (`crypto.py`)
- [ ] Exception hierarchy (`exceptions.py`)

### Phase 2: Abstractions
- [ ] Panel controllers (`panel.py`, `panel_sync.py`)
- [ ] Entity classes (`area.py`, `zone.py`, `output.py`)
- [ ] Constants module (`const/`)
- [ ] **VERIFY**: All DMP commands mapped to methods

### Phase 3: CLI & Documentation
- [ ] CLI tool (`utils/cli.py`)
- [ ] Examples and API docs
- [ ] **DMP command coverage matrix**

### Phase 4: Polish & Release
- [ ] **FINAL AUDIT**: All DMP panel commands implemented
- [ ] Security audit, testing (>80% coverage)
- [ ] PyPI package preparation

## Implementation Priority

**v0.1.0 (Core)**:
- Transport, authentication, encryption
- Basic area control (arm/disarm)
- Zone status, output control
- Error handling, CLI tool

**v0.2.0 (Enhanced)**:
- Additional arm modes (instant, night)
- Output pulse/toggle
- Emergency triggers
- State caching

**v0.3.0+ (Advanced)**:
- Panel configuration
- Event system
- Multiple panels
- Plugin architecture

## Testing Strategy

```python
# Mock panel for testing
class MockDMPPanel:
    async def handle_client(self, reader, writer):
        data = await reader.readline()
        command = data.decode().strip()

        if command.startswith("@00001!V2"):
            response = "OK: Authenticated\r\n"
        elif command == "@00001!S":
            response = "OK: Status\r\n"
        # ... handle other commands

        writer.write(response.encode())
        await writer.drain()
```

Coverage goals: 80%+ overall, 95%+ critical paths

## Security Considerations

- Never log credentials or keys
- Validate all inputs (account: 5 digits, zone: 1-999, code: 4-6 digits)
- Don't expose sensitive info in errors
- Support TLS if panel allows
- Rate limit commands (0.3s minimum)

## Configuration

```yaml
# config.yaml for CLI
panel:
  host: 192.168.1.100
  port: 2011
  account: "00001"
  remote_key: "ABCD1234"
```

## Technical Decisions

1. **Dual API**: Async (modern apps) + Sync (simple scripts)
2. **No global state**: All config via parameters
3. **Type hints**: Full mypy strict mode
4. **Logging**: Standard `logging` module
5. **State caching**: Optional with TTL
6. **Error handling**: Custom exception hierarchy

## pyproject.toml Essentials

```toml
[project]
name = "pydmp"
version = "0.1.0"
description = "Python library for controlling DMP alarm systems"
requires-python = ">=3.10"

[project.optional-dependencies]
dev = ["pytest>=7.4", "pytest-asyncio>=0.21", "black>=23.7", "mypy>=1.5"]
cli = ["click>=8.1", "pyyaml>=6.0", "rich>=13.0"]

[project.scripts]
pydmp = "pydmp.cli:main"
```

## Documentation (Zensical + mike)

Docs are built with [Zensical](https://zensical.org) (config: `zensical.toml`, content: `docs/`) and versioned with the [Zensical fork of mike](https://github.com/squidfunk/mike) at `https://amattas.github.io/pydmp/`. The mike fork is not on PyPI — CI installs it from GitHub pinned by commit (see `.github/workflows/docs.yml`).

### Version Mapping (handled by `docs.yml`)

| Trigger | Version | Alias |
|---------|---------|-------|
| Push to `main` | `dev` | none |
| Release published (stable) | `X.Y.Z` | `latest` (default) |
| Release published (alpha/beta) | `X.Y.Z` | none |
| `workflow_dispatch` with `version` input | as given | `latest` |

mike commits each built version to the `gh-pages` branch, which GitHub Pages serves directly (Pages source = `gh-pages` branch, classic mike setup).

### Local Testing
```bash
pip install -e ".[docs]"
pydoc-markdown -I src -p pydmp > docs/api/reference.md  # generated, gitignored
zensical serve  # http://127.0.0.1:8000/
```

### Troubleshooting
- Docs not updating: check [GitHub Actions](https://github.com/amattas/pydmp/actions) and that the `gh-pages` branch exists
- Version selector missing: ensure `zensical.toml` has `[project.extra.version]` with `provider = "mike"` and `default = "latest"`
- Wrong default: `mike set-default --push latest`

## License

MIT License

---

**Remember**: This is a **standalone library**. Keep it platform-agnostic, well-tested, and properly documented. Extract DMP protocol knowledge from references, not platform-specific code.
