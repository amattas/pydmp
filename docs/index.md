# PyDMP

PyDMP is a platform-agnostic Python library for controlling DMP (Digital Monitoring Products) alarm panels over TCP/IP. Built for developers who need reliable, straightforward access to DMP systems without vendor lock-in.

**Key Features:**

- **Dual APIs**: Choose async for modern applications or sync for simple scripts
- **High-level abstractions**: Work with panels, areas, zones, and outputs instead of raw protocol commands
- **Built-in rate limiting**: Automatic command throttling prevents panel overload
- **Real-time events**: Serial 3 (S3) status server with event parsing and callbacks
- **Type safety**: Full type hints throughout the codebase

## Installation

```bash
pip install pydmp
# CLI
pip install pydmp[cli]
# Docs (to build locally)
pip install pydmp[docs]
```

## Quick Start (Async)

```python
import asyncio
from pydmp import DMPPanel

async def main():
    panel = DMPPanel()
    await panel.connect("192.168.1.100", "00001", "YOURKEY")

    # Pull status (connect() is side-effect free)
    await panel.update_status()
    areas = await panel.get_areas()
    zones = await panel.get_zones()

    # Control
    await areas[0].arm(bypass_faulted=False, force_arm=False, instant=None)
    await areas[0].disarm()

    # Outputs
    outs = await panel.get_outputs()
    await outs[0].pulse()

    await panel.disconnect()

asyncio.run(main())
```

## Realtime Status (S3)

```python
import asyncio
from pydmp import DMPStatusServer, parse_s3_message

async def run():
    server = DMPStatusServer(host="127.0.0.1", port=5001)
    server.register_callback(lambda msg: print(parse_s3_message(msg)))
    await server.start()
    await asyncio.sleep(3600)

asyncio.run(run())
```

## Where to Next

- [Getting Started](guide/getting-started.md) - Installation, connection, and command flow
- [Panel Compatibility](compatibility.md) - Tested panels and compatibility reports
- [CLI Guide](guide/cli.md) - Command-line interface usage
- [Realtime Status (S3)](guide/realtime-status.md) - S3 listener and event parsing
- [Encryption & User Data](guide/encryption.md) - User code decryption and remote key behavior
- [Migration Guide](guide/migration.md) - Breaking API changes and upgrade notes
- [API Reference](api/panel.md) - Complete API documentation for Panel, Entities, Protocol, and more
