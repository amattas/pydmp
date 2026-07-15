# Getting Started

This guide walks you through connecting to your DMP panel, reading status, and sending commands.

## Core Concepts

Before diving in, here are a few key principles that shape how PyDMP works:

- **Single connection per panel**: PyDMP prevents multiple simultaneous connections to the same panel, protecting against state conflicts
- **Automatic rate limiting**: Commands are queued and sent one at a time with 0.3-second spacing to match panel expectations
- **Entity-based design**: Work with Areas (partitions), Zones (sensors), and Outputs (relays) rather than raw protocol strings

## Connect and Status

```python
from pydmp import DMPPanel

panel = DMPPanel()
await panel.connect(host="192.168.1.100", account="00001", remote_key="YOURKEY")
await panel.update_status()  # connect() is side-effect free; call explicit updates as needed

areas = await panel.get_areas()   # List[Area]
zones = await panel.get_zones()   # List[Zone]
outs  = await panel.get_outputs()  # List[Output] (1..4 are created on demand)
```

## Arm/Disarm

```python
# Arm single area
await areas[0].arm(bypass_faulted=False, force_arm=False, instant=None)
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

Use the realtime S3 server to receive events as they happen. See the [Realtime Status (S3)](realtime-status.md) guide for details.

```python
from pydmp import DMPStatusServer, parse_s3_message

server = DMPStatusServer(host="127.0.0.1", port=5001)
server.register_callback(lambda msg: print(parse_s3_message(msg)))
await server.start()
```

## Disconnect

```python
await panel.disconnect()
```
