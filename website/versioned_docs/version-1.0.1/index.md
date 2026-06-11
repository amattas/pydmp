---
slug: /
sidebar_position: 1
sidebar_label: Overview
title: PyDMP
---

import Link from '@docusaurus/Link';

PyDMP is a platform-agnostic Python library for controlling DMP (Digital
Monitoring Products) alarm panels over TCP/IP — dual async/sync APIs,
high-level panel/area/zone abstractions, built-in rate limiting, and real-time
S3 event handling. No vendor lock-in.

<div className="pd-cards">
  <Link className="pd-card" to="/guide/getting-started">
    <span className="pd-card-kicker">Guide</span>
    <span className="pd-card-title">Getting started</span>
    <span className="pd-card-desc">Installation, connecting to a panel, and the command flow.</span>
  </Link>
  <Link className="pd-card" to="/guide/cli">
    <span className="pd-card-kicker">Guide</span>
    <span className="pd-card-title">CLI</span>
    <span className="pd-card-desc">Drive panels from the command line with the bundled CLI.</span>
  </Link>
  <Link className="pd-card" to="/guide/realtime-status">
    <span className="pd-card-kicker">Guide</span>
    <span className="pd-card-title">Realtime status (S3)</span>
    <span className="pd-card-desc">Run the S3 status server and parse live panel events.</span>
  </Link>
  <Link className="pd-card" to="/guide/encryption">
    <span className="pd-card-kicker">Guide</span>
    <span className="pd-card-title">Encryption &amp; user data</span>
    <span className="pd-card-desc">User code decryption and remote key behavior.</span>
  </Link>
  <Link className="pd-card" to="/compatibility">
    <span className="pd-card-kicker">Reference</span>
    <span className="pd-card-title">Panel compatibility</span>
    <span className="pd-card-desc">Tested panels and community compatibility reports.</span>
  </Link>
  <Link className="pd-card" to="/api/reference">
    <span className="pd-card-kicker">Reference</span>
    <span className="pd-card-title">API reference</span>
    <span className="pd-card-desc">Panel, entities, protocol, and the S3 server — generated from docstrings.</span>
  </Link>
</div>

## Installation

```bash
pip install pydmp
# CLI
pip install pydmp[cli]
# Docs tooling (to build the API reference locally)
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

## Migration

Upgrading from an earlier version? See the [migration guide](guide/migration.md) for breaking API changes.
