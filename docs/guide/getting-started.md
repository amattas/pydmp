# Getting Started

This guide walks through connecting to a panel, reading status, and sending commands.

## Concepts

- One connection per panel: PyDMP guards against multiple active connections to the same host/port/account.
- Serialized I/O: Commands are sent one at a time with rate limiting (0.3s) to match panel expectations.
- Entities: Areas (partitions), Zones (lines), Outputs (relays) are high‑level abstractions.

## Connect and Status

```python
from pydmp import DMPPanel

panel = DMPPanel()
await panel.connect(host="192.168.1.100", account="00001", remote_key="YOURKEY")
await panel.update_status()

areas = await panel.get_areas()   # List[Area]
zones = await panel.get_zones()   # List[Zone]
outs  = await panel.get_outputs()  # List[Output] (1..4 are created on demand)
```

## Arm/Disarm

```python
# Arm single area
await areas[0].arm_away(bypass_faulted=False, force_arm=False, instant=None)
await areas[0].disarm()

# Arm multiple areas in one command
await panel.arm_areas([1, 2], bypass_faulted=True, force_arm=False, instant=True)
await panel.disarm_areas([1, 2])
```

## Zones and Outputs

```python
z = await panel.get_zone(1)
await z.bypass(); await z.restore()

o = await panel.get_output(1)
await o.pulse()
```

## Realtime Status

Use the realtime S3 server to receive events as they happen. See the dedicated page for details.

```python
from pydmp import DMPStatusServer, parse_scsvr_message

server = DMPStatusServer(host="0.0.0.0", port=5001)
server.register_callback(lambda msg: print(parse_scsvr_message(msg)))
await server.start()
```

## Disconnect

```python
await panel.disconnect()
```
