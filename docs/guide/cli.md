# Command-Line Interface (CLI)

PyDMP ships with a simple CLI for common operations. Install it with:

```bash
pip install pydmp[cli]
```

## Configuration

The CLI expects a YAML file with panel connection details (default: `config.yaml`).

```yaml
panel:
  host: 192.168.1.100
  account: "00001"
  remote_key: "YOURKEY"
```

Global options:
- `--config/-c PATH` — path to YAML file (default: `config.yaml`)
- `--debug` — verbose logs
Common flag:
- `--json` — output JSON instead of human-readable text (where applicable). For `listen`, `--json` outputs newline-delimited JSON (NDJSON).

## Commands

### Status
```bash
pydmp status [--json]
```
Connects and prints tables of areas and zones.

### Arm/Disarm (single area)
```bash
pydmp arm-away <AREA> [--bypass-faulted] [--force-arm] [--json]
pydmp arm-stay <AREA> [--bypass-faulted] [--force-arm] [--json]
pydmp disarm <AREA> [--json]
```
Sends `!C` with two flags by default; see multi‑area for the optional “instant” flag.

### Arm/Disarm (multiple areas)
```bash
pydmp arm-areas "1,2,3" [--bypass-faulted] [--force-arm] [--instant/--no-instant] [--json]
pydmp disarm-areas "1,2,3" [--json]
```
Concatenates the area numbers (e.g., `010203`) and sends a single `!C`/`!O` command. When `--instant` is provided, a third `Y/N` flag is appended to `!C`.

### Zones
```bash
pydmp bypass-zone <ZONE> [--json]
pydmp restore-zone <ZONE> [--json]
```
Sends `!X` or `!Y` for a 3‑digit zone number (e.g., `005`).

### Outputs
```bash
pydmp output <OUTPUT> on|off|pulse|toggle [--json]
```
Controls a 3‑digit output (`!Q001S`, `!Q001O`, `!Q001P`). Toggle flips between on and off.

### Sensor Reset
```bash
pydmp sensor-reset [--json]
```
Sends `!E001`.

### Users & Profiles
```bash
pydmp users [--json]
pydmp profiles [--json]
```
Fetches and prints decrypted user codes and user profiles. User code decryption uses the LFSR algorithm; mixing with a remote key is applied when provided and hex‑parsable.

### Realtime Status Listener
```bash
pydmp listen [--host 0.0.0.0] [--port 5001] [--duration 0] [--json]
```
Starts the S3 listener and prints parsed events. Use `Ctrl+C` to stop or `--duration` to exit after N seconds. With `--json`, each event is printed as a single line of JSON (NDJSON).

## Examples
```bash
# View status with a custom config and debug logs
pydmp --debug --config panel.yaml status

# Arm area 1 away (bypass faulted)
pydmp arm-away 1 --bypass-faulted

# Arm areas 1 and 2 with instant
pydmp arm-areas "1,2" --instant

# Bypass zone 5, pulse output 3
pydmp bypass-zone 5
pydmp output 3 pulse

# Fetch users and profiles (JSON)
pydmp users --json
pydmp profiles --json

# Listen for realtime events on port 6001 for 5 minutes
pydmp listen --port 6001 --duration 300

# JSON stream of events (pipe to jq)
pydmp listen --json --duration 10 | jq
```

## Notes
- The CLI uses the same async APIs. Commands serialize on a single connection with built‑in rate limiting.
- Some panels accept a blank/placeholder key for `!V2` auth; otherwise configure a valid `remote_key`.
- Only user‑code replies (`*P=`) are obfuscated; normal commands/status are plain ASCII.
