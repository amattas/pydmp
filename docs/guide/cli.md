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
- `--config, -c PATH` — path to YAML file (default: `config.yaml`)
- `--verbose, -v` — verbose logs (DEBUG)
- `--quiet, -q` — reduce logs (WARNING)
- `--debug, -d` — debug logs (overrides other flags)
- `--version, -V` — show version and exit
- `--help, -h` — show help

Common option:
- `--json, -j` — output JSON instead of human‑readable text (where applicable). For `listen`, `--json` outputs newline‑delimited JSON (NDJSON).

## Commands

### Areas & Zones
```bash
pydmp get-areas [--json|-j]
pydmp get-zones [--json|-j]
```
Print areas and zones separately.

### Arm/Disarm
```bash
pydmp arm "1,2,3" [--bypass-faulted|-b] [--force-arm|-f] [--instant|-i/--no-instant] [--json|-j]
pydmp disarm <AREA> [--json|-j]
```
`arm` accepts a comma‑separated list of areas and sends a single `!C` command. When `--instant` is provided, a third `Y/N` flag is appended to `!C`. `disarm` takes a single area and sends `!O`.

### Zones
```bash
pydmp set-zone-bypass <ZONE> [--json|-j]
pydmp set-zone-restore <ZONE> [--json|-j]
```
Sends `!X` or `!Y` for a 3‑digit zone number (e.g., `005`).

### Outputs
```bash
pydmp output <OUTPUT> on|off|pulse|toggle [--json|-j]
```
Controls a 3‑digit output (`!Q001S`, `!Q001O`, `!Q001P`). Toggle flips between on and off.

### Sensor Reset
```bash
pydmp sensor-reset [--json|-j]
```
Sends `!E001`.

### Users & Profiles
```bash
pydmp get-users [--json|-j]
pydmp get-profiles [--json|-j]
```
Fetches and prints decrypted user codes and user profiles. User code decryption uses the LFSR algorithm.

### Realtime Status Listener
```bash
pydmp listen [--host|-H 0.0.0.0] [--port|-p 5001] [--duration|-t 0] [--json|-j]
```
Starts the S3 listener and prints parsed events. Use `Ctrl+C` to stop or `--duration` to exit after N seconds. With `--json`, each event is printed as a single line of JSON (NDJSON).

## Examples
```bash
# View areas with a custom config and debug logs
pydmp --debug --config panel.yaml get-areas

# Arm area 1 (bypass faulted)
pydmp arm "1" --bypass-faulted

# Arm areas 1 and 2 with instant
pydmp arm "1,2" --instant

# Bypass zone 5, pulse output 3
pydmp set-zone-bypass 5
pydmp output 3 pulse

# Fetch users and profiles (JSON)
pydmp get-users --json
pydmp get-profiles --json

# Listen for realtime events on port 6001 for 5 minutes
pydmp listen --port 6001 --duration 300

# JSON stream of events (pipe to jq)
pydmp listen --json --duration 10 | jq
```

## Notes
- The CLI uses the same async APIs. Commands serialize on a single connection with built‑in rate limiting.
- Some panels accept a blank/placeholder key for `!V2` auth; otherwise configure a valid `remote_key`.
- Only user‑code replies (`*P=`) are obfuscated; normal commands/status are plain ASCII.
