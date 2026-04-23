# pydmp New-Core Examples

This folder is the clean starting point for the new stateless core.

The goal here is to give us a short set of examples that are easy to read, easy to run,
and easy to expand as the new core grows.

These examples are written for a source checkout. They add `pydmp/src` to `sys.path`
automatically, so you can run them directly from this repo without installing the package.

These examples focus on the Integrator connection:

- port `8011` for command and query traffic
- port `8001` for the push listener

This example set is aimed at XR150 and XR550 panels and should be treated as
tested for XR150/XR550 `v202` or higher.

No panel IP address is assumed. You must pass the target host explicitly.
The examples below use `192.168.1.123` as a placeholder.

## Real Hardware Setup

Before running the examples, make sure the panel is actually configured for the
Integrator lane.

### 1. Get the panel on the network

In the panel's network settings, make sure the panel itself has valid network
configuration.

If you are using DHCP:

- enable DHCP
- confirm the panel actually received a usable IP configuration on your LAN

If you are using static networking:

- set the panel Local IP Address
- set the panel Gateway Address
- set the panel Subnet Mask

The panel and the computer running these examples must be able to reach each
other both ways.

### 2. Configure the Integrator connection

In the Integrator programming section:

- set Integrator Connection to `NET`
- set Integrator Incoming TCP Port to `8011`
- set Integrator Outbound TCP Port to `8001`
- set Integrator IP Address to the IP address of the computer that will run the listener

The traffic split is:

- your computer connects to the panel on `8011` for commands and queries
- the panel connects back to your computer on `8001` for pushed events

### 3. Choose the session style

These examples intentionally support only two Integrator session styles:

- `blank_v2`
- `secure_s`

For `blank_v2`:

- leave the Integrator Passphrase blank in the panel
- do not pass `--passphrase` to the command examples

For `secure_s`:

- program an Integrator Passphrase in the panel
- pass the same value to the examples with `--passphrase`

Important limits for this example set:

- keyed V2 is not used here and should be treated as a no-go on the Integrator connection
- V30 and V31 are advanced topics and are intentionally left out of these examples

### 4. Turn on the report classes you need

For the listener to receive pushed events, Integrator reports must be enabled
in the panel.

At minimum, turn on the report classes you want to observe. Depending on what
you are testing, that usually means some combination of:

- arm/disarm reports
- zone reports
- user / schedule reports
- door access reports
- supervisory-style reports

If Integrator reports are off, `listen.py` can be running correctly and still
receive nothing.

## Recommended Starting Order

1. `query_areas.py`
   - Smallest read example.
   - Uses the beginner-friendly `CorePanelClient`.
2. `query_zones.py`
   - Shows a larger paged query and prints both areas and zones.
3. `query_area_settings.py`
   - Shows direct `CommandSessionManager` + transaction usage.
4. `query_zone_settings.py`
   - Shows a direct single-record settings read.
5. `query_users.py`
   - Walks the visible user table.
6. `query_profiles.py`
   - Walks the visible profile table.
7. `query_outputs.py`
   - Shows the output query options, including namespace selection.
8. `query_lockout_code.py`
   - Shows a very small read transaction.
9. `listen.py`
   - Starts the push listener, prints messages to the terminal, and writes a log file.
10. `sensor_reset.py`
11. `arm_areas.py`
12. `disarm_areas.py`
13. `bypass_zone.py`
14. `unbypass_zone.py`
15. `set_output.py`

The intended flow is:

- work through `1` to `9` first
- move on to `10` to `15` only after the read-only and monitoring examples are working as expected

## Transaction-to-Example Map

There is now one example script for each public transaction in `pydmp.core`.

### Read-Only and Monitoring

- `TransactionQueryAreas` -> `query_areas.py`
- `TransactionQueryZones` -> `query_zones.py`
- `TransactionQueryAreaSettings` -> `query_area_settings.py`
- `TransactionQueryZoneSettings` -> `query_zone_settings.py`
- `TransactionQueryUsers` -> `query_users.py`
- `TransactionQueryProfiles` -> `query_profiles.py`
- `TransactionQueryOutputs` -> `query_outputs.py`
- `TransactionQueryLockoutCode` -> `query_lockout_code.py`
- push listener / monitoring -> `listen.py`

### Writes and State-Changing Commands

- `TransactionSensorReset` -> `sensor_reset.py`
- `TransactionArmAreas` -> `arm_areas.py`
- `TransactionDisarmAreas` -> `disarm_areas.py`
- `TransactionBypassZone` -> `bypass_zone.py`
- `TransactionUnbypassZone` -> `unbypass_zone.py`
- `TransactionSetOutput` -> `set_output.py`

`TransactionWriteUser` is intentionally not represented here because it is still
kept experimental and off the public core surface.

## Session Modes

Most command examples default to `blank_v2`, because that is still the easiest
Integrator lane to start with when the panel passphrase is blank.

You can switch sessions with `--session-mode`:

- `blank_v2`
- `secure_s`

Each script exposes only the extra auth argument needed for those modes. For example:

```bash
python3 query_areas.py --host 192.168.1.123 --port 8011 --account 12345
python3 query_areas.py --host 192.168.1.123 --port 8011 --account 12345 --session-mode secure_s --passphrase 3333333333333333
```

## Read-Only and Monitoring Examples

Start here. These examples are intended to observe panel state, not change it.

- `query_areas.py`
  - Reads the authoritative area snapshot.
  - `python3 query_areas.py --host 192.168.1.123 --port 8011 --account 12345`

- `query_zones.py`
  - Reads the full area and zone snapshot.
  - `python3 query_zones.py --host 192.168.1.123 --port 8011 --account 12345`

- `query_area_settings.py`
  - Reads one `?Za` area-settings record.
  - `python3 query_area_settings.py --host 192.168.1.123 --port 8011 --account 12345 --area 4`

- `query_zone_settings.py`
  - Reads one `?ZL` zone-settings record.
  - `python3 query_zone_settings.py --host 192.168.1.123 --port 8011 --account 12345 --zone 1`

- `query_users.py`
  - Reads the visible `?P=` user table.
  - `python3 query_users.py --host 192.168.1.123 --port 8011 --account 12345`

- `query_profiles.py`
  - Reads the visible `?U` profile table.
  - `python3 query_profiles.py --host 192.168.1.123 --port 8011 --account 12345`

- `query_outputs.py`
  - Reads output status from `?WQ`.
  - `python3 query_outputs.py --host 192.168.1.123 --port 8011 --account 12345`
  - `python3 query_outputs.py --host 192.168.1.123 --port 8011 --account 12345 --namespace D --include-unnamed`

- `query_lockout_code.py`
  - Reads the programmer lockout code through `?ZZ`.
  - `python3 query_lockout_code.py --host 192.168.1.123 --port 8011 --account 12345`

- `listen.py`
  - Starts the Integrator listener on `8001` and writes a timestamped text log.
  - `python3 listen.py --listen-host 0.0.0.0 --listen-port 8001`
  - `python3 listen.py --listen-host 0.0.0.0 --listen-port 8001 --passphrase 3333333333333333`

## Write Examples

These examples can change live panel state.

Start with the read-only section above. Only move to this section after you
have confirmed that command sessions, account number, host addressing, and the
listener setup are all behaving the way you expect on the target panel.

Important warning:

- the `--confirm-live-write` flags reduce accidental execution
- this software may not completely protect you from malformed writes
- you are still responsible for checking selectors, area numbers, and panel state before sending a write

- `sensor_reset.py`
  - Sends `!E001`.
  - `python3 sensor_reset.py --host 192.168.1.123 --port 8011 --account 12345 --confirm-live-write`

- `arm_areas.py`
  - Sends one `!C` command for one or more areas.
  - `python3 arm_areas.py --host 192.168.1.123 --port 8011 --account 12345 --areas 1 2 --confirm-live-write`

- `disarm_areas.py`
  - Sends one `!O` command for one or more areas.
  - `python3 disarm_areas.py --host 192.168.1.123 --port 8011 --account 12345 --areas 1 2 --confirm-live-write`

- `bypass_zone.py`
  - Sends `!X` for one zone.
  - `python3 bypass_zone.py --host 192.168.1.123 --port 8011 --account 12345 --zone 1 --confirm-live-write`

- `unbypass_zone.py`
  - Sends `!Y` for one zone.
  - `python3 unbypass_zone.py --host 192.168.1.123 --port 8011 --account 12345 --zone 1 --confirm-live-write`

- `set_output.py`
  - Sends `!Q` for one output selector and one mode.
  - Poll outputs first and write only to selectors the panel already reported as valid.
  - Known tested modes:
    - `O`: turn the output off
    - `S`: turn the output on steadily
    - `P`: run a repeating pulse pattern
    - `M`: send one short momentary pulse
    - `T`: run the repeating triple-pulse pattern
  - The script also accepts the friendly aliases `off`, `on`, `steady`, `pulse`, and `momentary`.
  - The still-questionable modes `W`, `a`, and `t` are intentionally not documented here.
  - `python3 set_output.py --host 192.168.1.123 --port 8011 --account 12345 --output 1 --mode S --confirm-live-write`

## Notes

- `set_output.py` is intentionally conservative. Poll outputs first and keep writes limited
  to selectors that the panel already reported as valid.
- The listener example writes a timestamped log file under `examples/logs/` unless you pass
  `--log-path`.
- The listener examples assume the panel is configured to send Integrator push traffic to
  the host and port you selected.
- These examples are meant to be readable first. If we need more advanced scripts later,
  we can add them without turning this folder back into a catch-all dump.
