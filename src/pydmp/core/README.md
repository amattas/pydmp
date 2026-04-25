# pydmp.core

`pydmp.core` is the new stateless protocol layer for PyDMP.

It is meant to be the reliable engine underneath higher-level APIs. It knows
how to open panel command sessions, run one transaction at a time, parse the
reply, and close idle sessions. It does not try to own long-lived panel state,
Home Assistant entities, or application caches.

The older `pydmp` package surface was built around one stateful panel object.
The new core is different on purpose:

- command/query behavior lives in small transaction classes
- session handling lives in reusable session profiles
- push listening is separate from command sessions
- callers can choose a friendly client or lower-level transaction manager
- raw wire replies remain available for diagnostics

## Current Shape

The core is organized around a few small building blocks.

`PanelEndpoint`
: Stores the panel host, port, account number, remote key, timeout, and idle
disconnect settings.

`PanelTransport`
: Owns the TCP socket used by command/query sessions.

`SessionProfile`
: Opens, uses, and closes one session style. The current profiles are blank
`!V2`, keyed `!V2`, wrapped `V30`, wrapped `V31`, and secure `!!S`.

`CommandSessionManager`
: Queues transactions for one endpoint. It opens a session when work arrives,
runs transactions one at a time, and closes the session after it has been idle.

`Transaction`
: Represents one command or query. A transaction supplies the request body,
the reply expectation, and an optional parser.

`CorePanelClient`
: A beginner-friendly async client with one method per common transaction.

`DMPPushListener`
: A TCP listener for panel-initiated push traffic. It ACKs supported push
frames, parses known event families, and leaves unknown event shapes available
as raw events.

## Command And Query Flow

Most command/query calls follow the same path:

1. Application code creates a `PanelEndpoint`.
2. Application code chooses a session profile, or lets the client default to
blank `!V2`.
3. A `CommandSessionManager` creates a TCP transport for that endpoint.
4. The caller submits a transaction.
5. The manager opens the selected session if one is not already open.
6. The selected session profile formats the transaction for the active session.
7. The panel reply is passed back to the transaction parser.
8. The caller receives a typed reply object.
9. The manager closes the session after the configured idle delay.

This is intentionally queue-based. A panel command session should only have one
active command in flight at a time. Callers can submit from multiple tasks, but
the manager serializes the actual wire traffic.

## Friendly Client Example

`CorePanelClient` is the easiest place to start. It exposes named helpers and
keeps the transaction details out of the first example.

```python
import asyncio

from pydmp.core import CorePanelClient, PanelEndpoint


async def main() -> None:
    endpoint = PanelEndpoint(host="192.168.1.123", port=8011, account="12345")
    client = CorePanelClient(endpoint)

    try:
        areas = await client.query_areas()
        for area in areas.records:
            print(area.number, area.state, area.name)
    finally:
        await client.close()


asyncio.run(main())
```

## Direct Transaction Example

Use `CommandSessionManager` directly when a script needs precise control over
which transaction is submitted.

```python
import asyncio

from pydmp.core import CommandSessionManager, PanelEndpoint, TransactionQueryZones


async def main() -> None:
    endpoint = PanelEndpoint(host="192.168.1.123", port=8011, account="12345")
    manager = CommandSessionManager(endpoint)

    try:
        completed = await manager.submit(TransactionQueryZones())
        reply = completed.parsed_response
        print(f"areas={len(reply.areas)} zones={len(reply.zones)}")
    finally:
        await manager.close()


asyncio.run(main())
```

## Session Modes

The core currently supports these command/query session profiles.

`SessionProfileBlankV2`
: Blank local `!V2`. This is the default for `CorePanelClient` and the simplest
Integrator starting point when the panel passphrase is blank.

`SessionProfileKeyedV2`
: Local `!V2` with a remote key appended to the session request. This is useful
for panel paths that expect a remote key, but it is not the default Integrator
example path.

`SessionProfileV30`
: Wrapped local V3 mode that uses a user code and panel serial value.

`SessionProfileV31`
: Wrapped local V3 mode that uses compare material instead of a user code.

`SessionProfileSecureS`
: Secure `!!S` mode using a passphrase. This is the recommended secure
Integrator path when a panel passphrase is configured.

The examples folder intentionally keeps the public hardware examples focused on
blank `!V2` and secure `!!S`. V3 modes are available in the core for callers
that already understand the required inputs.

## Public Transactions

The public transaction set is split into read-only transactions and
state-changing transactions.

Read-only transactions:

- `TransactionQueryAreas`: authoritative area status from `?WA`
- `TransactionQueryZones`: full area-seeded zone status from `?WB`
- `TransactionQueryAreaSettings`: one area settings record from `?ZaNN`
- `TransactionQueryZoneSettings`: one zone settings record from `?ZLNNN`
- `TransactionQueryUsers`: visible user table from `?P=`
- `TransactionQueryProfiles`: visible profile table from `?U`
- `TransactionQueryOutputs`: output status from `?WQ`
- `TransactionQueryLockoutCode`: programmer lockout code from `?ZZ`

State-changing transactions:

- `TransactionSensorReset`: sensor reset through `!E001`
- `TransactionArmAreas`: arm one or more areas through `!C`
- `TransactionDisarmAreas`: disarm one or more areas through `!O`
- `TransactionBypassZone`: bypass one zone through `!X`
- `TransactionUnbypassZone`: restore one zone through `!Y`
- `TransactionSetOutput`: set one output selector through `!Q`

`TransactionWriteUser` exists in the users module, but it is intentionally not
part of the public `pydmp.core` export surface yet. User writes need more
real-world safety work before they should be easy to call by accident.

## Important Query Behavior

Some transactions do more than send one request and parse one reply.

`TransactionQueryAreas`
: Uses `?WA` as the authoritative source for area status. The reply includes
area number, name, area state, schedule-active state, and late-to-close state.

`TransactionQueryZones`
: First queries areas, then polls each area's `?WB` stream to completion. This
is important because area-specific zones may only appear when their own area is
used as the seed. Duplicate global zones are de-duplicated in the final result.

`TransactionQueryOutputs`
: Polls one output namespace at a time. Numeric outputs are the default. `D`,
`F`, and `G` namespaces must be requested explicitly. By default, unnamed and
`* UNUSED *` outputs are filtered from the returned `records`, while all parsed
rows remain available in `all_records`.

`TransactionQueryUsers` and `TransactionQueryProfiles`
: Walk by selector progress. Each next query is based on the highest returned
record plus one. This avoids assuming that page size alone means the table is
complete.

## Writes And Safety

The write transactions are intentionally narrow:

- area arm/disarm commands take area numbers and normalize them to panel form
- bypass and unbypass write exactly one zone per command
- output writes accept parser-valid output selectors but do not prove that a
selector is meaningful on the current panel

Applications should poll first and write second. For example, use
`TransactionQueryOutputs` before `TransactionSetOutput`, and keep output writes
limited to selectors the target panel actually reports or that the operator has
otherwise confirmed.

The core validates known command shapes, but it cannot protect every possible
panel configuration or operating-state mistake.

## Push Listener Flow

Command sessions and push traffic are separate. The command manager opens a
client connection to the panel. The listener accepts panel-initiated
connections.

Basic listener flow:

1. Application code creates a `DMPPushListener`.
2. The panel connects to the listener port when it has a pushed event.
3. The listener decodes clear or secure `!!S` push traffic.
4. Supported frames are ACKed.
5. The listener creates a `PushMessage`.
6. Any recognized event family gets a typed `PushEvent.parsed` object.
7. Unknown event families still produce raw events for logging and later parser
work.

The listener parser registry is deliberately modular. New event parsers can be
added without changing the socket server or callback flow.

Currently parsed event families include common area, zone, system, access,
schedule, user-code, and check-in style pushes. The parsed event also exposes a
friendly application layer:

- `event.group`
- `event.kind`
- `event.action`
- `event.type_code`
- `event.type_name`
- `event.target_id`
- `event.target_name`
- `event.actor_id`
- `event.actor_name`
- `event.summary`

When a parser is not available, callers still receive the raw event body and
split fields. This keeps the listener useful while the event catalog continues
to grow.

## Error Handling

The core has a small error hierarchy rooted in `CommandSessionError` for
command/query work and `ListenerError` for push listening.

Common command/session errors include:

- `SessionConnectError`
- `SessionHandshakeError`
- `SessionProtocolError`
- `SessionTimeoutError`
- `TransactionParseError`

The manager separates wire errors from parse errors. A transaction can complete
at the socket/session level and still raise `TransactionParseError` if the reply
does not match the parser's expected shape.

## Examples

Runnable examples live in the repository-level `examples/` folder. That folder
contains one script for each public transaction plus a listener example. Start
with read-only examples, then move to write examples only after command/query
and listener setup are working on the target panel.

The examples focus on the Integrator connection:

- command/query traffic on port `8011`
- push listener traffic on port `8001`

See `examples/README.md` for hardware setup notes and exact commands.

## Compatibility Layer

The new core is not the old stateful API. A compatibility wrapper exists under
`pydmp.wrapper` for code that expects the original `DMPPanel`, `Area`, `Zone`,
and `Output` style objects.

That wrapper is a migration aid. New code should prefer `pydmp.core` directly
unless it specifically needs the older stateful surface.

