# Migration Guide

This page highlights recent breaking changes that removed temporary compatibility aliases and shims.

## Removed Aliases

- `DMPConnection` - use `DMPTransport`
- `DMPConnectionSync` - use `DMPTransportSync`
- `DMPCommandNAK` - use `DMPCommandNAKError`

These were transitional names kept during refactors and are now removed to keep the public API consistent.

## Panel Command Shim Removed

`DMPPanel` no longer falls back to a connection object that implements a `send_command(...)` coroutine. The panel always uses its configured `DMPTransport` and `DMPProtocol` to encode and send bytes.

If you previously injected a stub connection with a `send_command` for tests, update your tests to either:

- Patch `panel._send_command` to route through your stub, or
- Provide a lightweight fake `DMPTransport`/`DMPProtocol` if you want to exercise encoding/decoding.

Example (tests):

```python
panel = DMPPanel()
panel._connection = FakeConnection()
panel._send_command = panel._connection.send_command
```

## Notes on Legacy Fields

The user code model (`UserCode`) still includes `temp_date` and `exp_date` as legacy fields for clarity, in addition to the clarified `start_date` and `end_date`. These are not aliases and remain available.
