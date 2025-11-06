# PyDMP

PyDMP is a platform‑agnostic Python library to control DMP (Digital Monitoring Products) alarm panels over TCP.

- Async and sync APIs
- High‑level entities (Panel, Areas, Zones, Outputs)
- Protocol encoder/decoder with rate limiting and single‑connection guard
- Realtime Serial 3 (S3) status server with callbacks
- User code decryption and profile parsing

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

    # Pull status
    await panel.update_status()
    areas = await panel.get_areas()
    zones = await panel.get_zones()

    # Control
    await areas[0].arm_away(bypass_faulted=False, force_arm=False, instant=None)
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
from pydmp import DMPStatusServer, parse_scsvr_message

async def run():
    server = DMPStatusServer(host="0.0.0.0", port=5001)
    server.register_callback(lambda msg: print(parse_scsvr_message(msg)))
    await server.start()
    await asyncio.sleep(3600)

asyncio.run(run())
```

## Where to Next

- Guide → Getting Started covers install, connect, command flow
- Guide → Realtime Status shows S3 listener + parsing
- Guide → Encryption explains user code decryption and remote key behavior
- API Reference documents all classes and methods with type hints

