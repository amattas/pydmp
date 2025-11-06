# Realtime Status (Serial 3)

PyDMP can run a lightweight TCP server that accepts Serial 3 (S3) Z‑messages pushed by the panel. You can parse each message into a structured event and update your application accordingly.

## Start the Server

```python
import asyncio
from pydmp import DMPStatusServer, parse_s3_message

async def on_start():
    server = DMPStatusServer(host="127.0.0.1", port=5001)

    def on_event(msg):
        evt = parse_s3_message(msg)
        print(evt.category, evt.type_code, evt.area, evt.zone, evt.device)

    server.register_callback(on_event)
    await server.start()

asyncio.run(on_start())
```

## Mapping to Constants

- Event category (Za/Zq/Zc/…): `DMPEventType`
- Type code within category:
  - Arming (Zq): `DMPArmingEvent` (OP/CL/LA)
  - Real‑time (Zc): `DMPRealTimeStatusEvent` (DO/DC/ON/OF/PL/TP)
  - Zone events (Za/Zr/Zt/Zw/Zx/Zy): `DMPZoneEvent` (BL/FI/BU/…)
  - User codes (Zu): `DMPUserCodeEvent` (AD/CH/DE/IN)
  - Schedules (Zl): `DMPScheduleEvent`
  - Holidays (Zg): `DMPHolidayEvent`
  - Equipment (Ze): `DMPEquipmentEvent`
  - System message (Zs): `SYSTEM_MESSAGES[code]`

Use `parse_s3_message` to build a `ParsedEvent` with both raw codes and typed enums.

## ACK Behavior

The server automatically ACKs each incoming message with: `STX + [5‑byte account] + 0x06 + CR`. This prevents panel retries.

## Auto‑Refreshing User Cache

If you already have a `DMPPanel` instance, you can attach the status server so user code (Zu) events automatically refresh the panel’s user cache:

```python
from pydmp import DMPPanel, DMPStatusServer

panel = DMPPanel()
# ... connect panel ...
server = DMPStatusServer(host="127.0.0.1", port=5001)
panel.attach_status_server(server)
```

Detach later with `panel.detach_status_server(server)`.
