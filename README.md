# PyDMP

**Python library for controlling DMP (Digital Monitoring Products) alarm systems**

[![Tests](https://img.shields.io/badge/tests-passing-green.svg)](https://github.com/yourusername/pydmp)
[![Coverage](https://img.shields.io/badge/coverage-41%25-yellow.svg)](https://github.com/yourusername/pydmp)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

PyDMP is a standalone, platform-agnostic Python library for interfacing with DMP alarm panels via TCP/IP. It provides both asynchronous and synchronous APIs with full type hints, comprehensive error handling, and automatic rate limiting.

> Status: Work in progress — under active development. Interfaces and CLI commands may change between releases.

## Features

- ✅ **Low-level protocol communication** with DMP panels
- ✅ **High-level abstractions** (panels, areas, zones, outputs)
- ✅ **Both sync and async APIs** with automatic rate limiting
- ✅ **Full type hints** and comprehensive error handling
- ✅ **LFSR encryption** for user codes
- ✅ **CLI tool** for command-line control
- ✅ **Platform-independent** - not tied to any home automation system

## Installation

```bash
pip install pydmp
```

### CLI Tool Installation

For the command-line interface:

```bash
pip install pydmp[cli]
```

### Development Installation

For development with tests:

```bash
pip install -e ".[dev]"
```

## Quick Start

### Async API (Recommended)

```python
import asyncio
from pydmp import DMPPanel

async def main():
    panel = DMPPanel()
    await panel.connect("192.168.1.100", "00001", "YOUR_KEY")

    # Arm/disarm area
    areas = await panel.get_areas()
    await areas[0].arm(bypass_faulted=True)  # Optional flags; instant can be set too
    await areas[0].disarm()

    # Check status (raw codes: A/D/S)
    state = await areas[0].get_state()
    if state == 'A':
        print("Armed (Away)")

    # Check zones (raw codes: N/O/S/X/L/M)
    zones = await panel.get_zones()
    for zone in zones:
        if zone.is_open:
            print(f"Open zone: {zone.number} - {zone.name}")

    await panel.disconnect()

asyncio.run(main())
```

### Sync API (Simple Scripts)

```python
from pydmp import DMPPanelSync

panel = DMPPanelSync()
panel.connect("192.168.1.100", "00001", "YOUR_KEY")

areas = panel.get_areas()
areas[0].arm_sync()

state = areas[0].get_state_sync()
if state == 'A':
    print("Armed (Away)")

panel.disconnect()
```

## API Documentation

### Panel Control

```python
# Connect to panel (side-effect free)
await panel.connect(host, account, remote_key)

# Get entities
areas = await panel.get_areas()  # List[Area]
zones = await panel.get_zones()  # List[Zone]
outputs = await panel.get_outputs()  # List[Output]

# Update status (explicit)
await panel.update_status()

# Disconnect
await panel.disconnect()
```

### Area Control

```python
area = await panel.get_area(1)

# Arming (no user code required)
await area.arm()
await area.arm(bypass_faulted=True)  # Bypass faulted zones
await area.arm(force_arm=True)  # Force arm bad zones
await area.disarm()  # No user code sent to panel

# Status
state = area.state  # AreaState enum
is_armed = area.is_armed
is_disarmed = area.is_disarmed
```

### Zone Control

```python
zone = await panel.get_zone(1)

# Zone operations
await zone.bypass()
await zone.restore()

# Status
state = zone.state  # ZoneState enum
is_open = zone.is_open
is_bypassed = zone.is_bypassed
has_fault = zone.has_fault
```

### Output Control

```python
output = await panel.get_output(1)

# Output operations
await output.turn_on()
await output.turn_off()
await output.pulse()
await output.toggle()

# Status
state = output.state  # OutputState enum
is_on = output.is_on
```

## CLI Usage

### Configuration

Create a `config.yaml` file:

```yaml
panel:
  host: 192.168.1.100
  account: "00001"
  remote_key: "YOUR_KEY"
```

JSON output

- Most commands support `--json` to emit machine-readable JSON. The default output is a human-friendly table/message format. The `listen` command streams newline-delimited JSON (NDJSON) when `--json` is provided.

### Commands

```bash
# Get areas and zones
pydmp get-areas
pydmp get-zones

# Arm area(s)
pydmp arm "1,2"

# Disarm area (no user code needed)
pydmp disarm 1

# Zone control
pydmp bypass-zone 5
pydmp restore-zone 5

# Output control
pydmp output 1 on
pydmp output 2 off
pydmp output 3 pulse
pydmp output 4 toggle

# JSON output examples
pydmp status --json
pydmp users --json
pydmp profiles --json
pydmp listen --json --duration 10 | jq
```

## DMP Protocol Details

### Connection
- **Protocol**: TCP/IP
- **Port**: 2011 (default)
- **Format**: `@[ACCOUNT][COMMAND]\r`
- **Account**: 5 digits, left-padded (e.g., `00001`)
- **Rate Limit**: 0.3s minimum between commands

### Command Format Notes
- **[AA]**: 2-digit area number (01-08)
- **[ZZZ]**: 3-digit zone number (001-999)
- **[NNN]**: 3-digit output number (001-999)
- **[B]**: Bypass faulted zones (Y/N)
- **[F]**: Force arm (Y/N)
- **[M]**: Output mode (O=Off, P=Pulse, S=Steady, M=Momentary)

### Core Commands

| Command | Description | Format |
|---------|-------------|--------|
| `!V2[KEY]` | Authenticate | `@[ACCT]!V2[KEY]\r` |
| `!V0` | Drop connection | `@[ACCT]!V0\r` |
| `!S` | Get status | `@[ACCT]!S\r` |
| `?WB**Y001` | Get zone/area status | `@[ACCT]?WB**Y001\r` |
| `!O[AA]` | Disarm area | `@[ACCT]!O01\r` |
| `!C[AA],[B][F]` | Arm area | `@[ACCT]!C01,NN\r` |
| `!X[ZZZ]` | Bypass zone | `@[ACCT]!X005\r` |
| `!Y[ZZZ]` | Restore zone | `@[ACCT]!Y005\r` |
| `!Q[NNN][M]` | Set output | `@[ACCT]!Q001P\r` |

## Architecture

```
pydmp/
├── transport.py         # Async TCP transport (raw bytes I/O)
├── transport_sync.py    # Sync wrapper (transport + protocol)
├── protocol.py          # DMP protocol encoder/decoder
├── crypto.py            # LFSR encryption
├── panel.py             # Async panel controller
├── panel_sync.py        # Sync panel controller
├── status_server.py     # Serial 3 (S3) realtime listener
├── status_parser.py     # Parse S3 Z-frames to typed events
├── user.py              # User code model
├── profile.py           # User profile model
├── area.py              # Area abstraction
├── zone.py              # Zone abstraction
├── output.py            # Output abstraction
├── const/               # Constants (states, types, commands)
├── exceptions.py        # Exception hierarchy
└── cli.py               # CLI tool
```

## Error Handling

PyDMP provides a comprehensive exception hierarchy:

```python
from pydmp.exceptions import (
    DMPError,               # Base exception
    DMPConnectionError,     # Connection issues
    DMPAuthenticationError, # Auth failed
    DMPTimeoutError,        # Operation timeout
    DMPProtocolError,       # Protocol errors
    DMPCommandNAK,         # Command rejected
    DMPAreaError,          # Area-specific errors
    DMPZoneError,          # Zone-specific errors
    DMPOutputError,        # Output-specific errors
)
```

## Security Considerations

- Never log credentials or keys
- Validate all inputs (account: 5 digits, zone: 1-999, code: 4-6 digits)
- Don't expose sensitive info in errors
- Support TLS if panel allows
- Rate limit commands (0.3s minimum)

## Development

```bash
# Clone repository
git clone https://github.com/yourusername/pydmp.git
cd pydmp

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=pydmp --cov-report=html

# Format code
black src/ tests/

# Type checking
mypy src/

# Linting
ruff check src/ tests/
```

## Documentation

Online docs (MkDocs + mkdocstrings) include concepts, realtime status (S3), encryption details, and full API reference.

- Build locally:

```bash
pip install -e ".[docs]"
mkdocs serve
```

- CI deploys docs to GitHub Pages on push to main.

## Testing

PyDMP includes comprehensive unit tests for core functionality:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_protocol.py

# Run with coverage
pytest --cov=pydmp --cov-report=term-missing
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Future Enhancements

### Emergency Triggers
Emergency events (Panic, Fire, Police, Medical) are not yet implemented. In the reference implementation, these are triggered by pulsing configurable output relays rather than sending dedicated panel commands. For example:
- Configure which output number corresponds to each emergency type
- Trigger emergency by pulsing that output: `!Q[output]P`

This functionality may be added in a future version.

## Disclaimer

This is an independent project and is not affiliated with, endorsed by, or associated with Digital Monitoring Products (DMP).

## Support

- **Issues**: https://github.com/yourusername/pydmp/issues
- **Documentation**: https://github.com/yourusername/pydmp/wiki
- **Discussions**: https://github.com/yourusername/pydmp/discussions

---

Made with ❤️ for the home automation community
