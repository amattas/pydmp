# DMP XR500 API Reference

This document provides a structured reference for all commands supported by the DMP XR500 alarm control panel via Simpl+ drivers. Each entry details the command syntax, parameters, description, and expected responses.

 ## Table of Contents
 - [Panel Commands](#panel-commands)
   - [Login (`!V2`)](#login-v2)
   - [Sensor Reset (`!E001`)](#sensor-reset-e001)
   - [Keep Alive (`!H`)](#keep-alive-h)
   - [Get MAC & Serial (`?ZX1`)](#get-mac-and-serial-zx1)
   - [Get Software Version (`? `)](#get-software-version)
   - [Get System Status (`?WS`)](#get-system-status)
   - [Get User Codes (`?P=`)](#get-user-codes-p)
   - [Get User Profiles (`?U`)](#get-user-profiles-u)
   - [Query Output Status (`?WQ`)](#query-output-status-wq)
   - [Query Zone Status (`?WB`)](#query-zone-status-wb)
 - [Area Commands](#area-commands)
   - [Arm Area (`!C`)](#arm-area-c)
   - [Disarm Area (`!O`)](#disarm-area-o)
   - [Query Area Status (`?WB`)](#query-area-status-wb)
 - [Home/Sleep/Away Commands](#homesleepaway-commands)
   - [Arm Home (`!C01`)](#arm-home-c01)
   - [Arm Sleep (`!C0102`)](#arm-sleep-c0102)
   - [Arm Away (`!C010203`)](#arm-away-c010203)
   - [Disarm All (`!O010203`)](#disarm-all-o010203)
   - [Query Status (`?WBxx`)](#query-status-wbxx)
 - [Output Control Commands](#output-control-commands)
   - [Turn On Steady (`!Q…S`)](#turn-on-steady-qs)
   - [Turn Off (`!Q…O`)](#turn-off-qo)
   - [Turn On Pulse (`!Q…P`)](#turn-on-pulse-qp)
   - [Turn On Momentary (`!Q…M`)](#turn-on-momentary-qm)
   - [Turn On Temporal Code 3 (`!Q…T`)](#turn-on-temporal-code-3-qt)
 - [Zone Commands](#zone-commands)
   - [Query Zone Details (`?WB`)](#query-zone-details-wb)
   - [Bypass Zone (`!X`)](#bypass-zone-x)
   - [Reset Zone (`!Y`)](#reset-zone-y)

 ## Panel Commands

 ### Login (`!V2`)
 **Format**: `!V2<RemoteKey>\r`
 - `<RemoteKey>`: Remote key string for authentication
 **Example**:
 ```
 !V2A1B2C3D4\r   // Login with remote key A1B2C3D4
 ```
 **Response**:
 - `+V2<RemoteKey>` on success
 - `-V2<RemoteKey>` on failure

 ### Sensor Reset (`!E001`)
 **Format**: `!E001\r`
 **Example**:
 ```
 !E001\r   // Reset sensors
 ```
 **Response**:
 - `+E001` on success
 - `-E001` on failure

 ### Keep Alive (`!H`)
 **Format**: `!H\r`
 **Example**:
 ```
 !H\r   // Keep alive
 ```
 **Response**:
 - `+H` on success
 - `-H` on failure

 ### Get MAC & Serial (`?ZX1`)
 **Format**: `?ZX1\r`
 **Example**:
 ```
 ?ZX1\r   // Get MAC address and serial number
 ```
 **Response**:
 - Starts with `ZX1`
 - Characters 3–14: MAC address (12 hex digits)
 - Characters 15–: Serial number (variable length)
 **Example Response**:
 ```
 \xFEZX1AABBCCDDEEFF12345678\xFF
 ```

 ### Get Software Version (`? `)
 **Format**: `? \r`
 **Example**:
 ```
 ? \r   // Get software version and model number
 ```
 **Response**:
 - Starts with a space
 - Characters 2–5: Software version
 - Characters 6–9: Model number
 **Example Response**:
 ```
 \xFE 0101XR500\xFF
 ```

 ### Get System Status (`?WS`)
 **Format**: `?WS\r`
 **Example**:
 ```
 ?WS\r   // Query system status
 ```
 **Response**:
 - Starts with `WS`
 - Following characters: Telephone Line 1 status, AC power status, battery status, tamper status, printer status, wireless status, Telephone Line 2 status (each one character)
 **Example Response**:
 ```
 \xFEWSNTNTRN\xFF
 ```

 ### Get User Codes (`?P=`)
 **Format**: `?P=<UserNumber>\r`
 - `<UserNumber>`: 4-digit number, 0000–9999
 **Example**:
 ```
 ?P=0000\r   // Request all user codes starting at 0000
 ```
 **Response**:
 - Starts with `P=`
 - Encrypted user data (parsed in multiple `P=` messages)
 **Example Response**:
 ```
 \xFEP=0001F2345...----\xFF
 ```

 ### Get User Profiles (`?U`)
 **Format**: `?U<ProfileNumber>\r`
 - `<ProfileNumber>`: 3-digit number, 000–999
 **Example**:
 ```
 ?U000\r   // Request all user profiles
 ```
 **Response**:
 - Starts with `U`
 - Profile data (parsed in multiple `U` messages)
 **Example Response**:
 ```
 \xFEU001...----\xFF
 ```

 ### Query Output Status (`?WQ`)
 **Format**: `?WQ<OutputNumber>\r`
 - `<OutputNumber>`: 3-digit string, e.g., "001"
 **Example**:
 ```
 ?WQ005\r   // Query status for output 5
 ```
 **Response**: Same as [Output Control Commands > Response].

 ### Query Zone Details (`?WB`)
 **Initial Format**: `?WB**Y<StartZoneNumber>\r`
 **Continued Format**: `?WB\r`
 - `<StartZoneNumber>`: 3-digit, 001–999
 **Description**:
 Retrieves all zone definitions and status in multiple chunks. Send the initial command with the starting zone number (typically `001`) to receive the first block of zone records. Each response contains one or more zone records separated by ASCII 30 (`\x1E`), ending with a dash (`-`) to indicate more records are available. After a response ending in `-`, send `?WB\r` (no parameters) to retrieve the next block. Repeat until the panel returns `*WB-`, indicating the end of the list.
 **Response Packet Format**:
 - Payload begins after the `*WB` header.
 - Zone records:
   - `A<AreaNumber>`: assigns subsequent zones to the specified area.
   - `L<ZoneNumber><Status><ZoneName>`: zone entry, where:
     - `<ZoneNumber>`: 3-digit ID.
     - `<Status>`: `N`=Normal, `O`=Open, `S`=Short, `X`=Bypassed, `L`=Low Battery, `M`=Missing.
     - `<ZoneName>`: up to 16 characters.
 - Records are separated by `\x1E` and the packet ends with `-`.
 **Example**:
 ```
 ?WB**Y001\r
 *WBA001L001NFront Door\x1EL002NBack Door\x1E-
 ?WB\r
 *WBL003NGarage Door\x1EL004NPatio Door\x1E-
 ?WB\r
 *WB-
 ```

## Area Commands

 ### Arm Area (`!C`)
 **Format**: `!C<AreaNumber>,<BypassFlag><ForceFlag>\r`
 - `<AreaNumber>`: 2-digit, 01–99
 - `<BypassFlag>`: Y = bypass bad zones, N = do not bypass
 - `<ForceFlag>`: Y = force bad zones, N = do not force
**Example**:
```
!C01,NY\r   // Arm area 1, bypass = N, force = Y
```
**Response** (Area Status):
 - Position 2: `A` (Area status message)
 - Characters 3–5: Area number (3 digits)
 - Characters 7–22: User name (16 chars)
 - Characters 24–39: Area name (16 chars)
 - Second-to-last character: Status (1 = armed, 0 = disarmed)
  
**Example Response**:
```
\xFEA001\JOHN DOE        \MAIN LOBBY       1\xFF
```

 ### Disarm Area (`!O`)
 **Format**: `!O<AreaNumber>,\r`
 - `<AreaNumber>`: 2-digit, 01–99
 - Comma is required even with no parameters.
**Example**:
```
!O01,\r   // Disarm area 1
```
**Response**: Same as Arm Area status response.
  
**Example Response**:
```
\xFEA001\JOHN DOE        \MAIN LOBBY       0\xFF
```

 ### Query Area Status (`?WB`)
 **Format**: `?WB<AreaNumber>Y001\r`
 - `<AreaNumber>`: 2-digit, 01–99
**Example**:
```
?WB01Y001\r   // Query status for area 1
```
**Response**: Same as Area status response.
  
**Example Response**:
```
\xFEA001\JOHN DOE        \MAIN LOBBY       1\xFF
```

 ## Home/Sleep/Away Commands

 ### Arm Home (`!C01`)
 **Format**: `!C01,<BypassFlag><ForceFlag>\r`
  Arms Home mode (area 1).
**Response**: One Area status message (see [Area Commands > Response]).
  
**Example Response**:
```
\xFEA001\JOHN DOE        \HOME MODE        1\xFF
```

 ### Arm Sleep (`!C0102`)
 **Format**: `!C0102,<BypassFlag><ForceFlag>\r`
  Arms Sleep mode (areas 1 + 2).
**Response**: Two Area status messages, one per area (see [Area Commands > Response]).
  
**Example Responses**:
```
\xFEA001\JOHN DOE        \HOME MODE        1\xFF
\xFEA002\JOHN DOE        \SLEEP MODE       1\xFF
```

 ### Arm Away (`!C010203`)
 **Format**: `!C010203,<BypassFlag><ForceFlag>\r`
  Arms Away mode (areas 1 + 2 + 3).
**Response**: Three Area status messages, one per area (see [Area Commands > Response]).
  
**Example Responses**:
```
\xFEA001\JOHN DOE        \HOME MODE        1\xFF
\xFEA002\JOHN DOE        \SLEEP MODE       1\xFF
\xFEA003\JOHN DOE        \AWAY MODE        1\xFF
```

 ### Disarm All (`!O010203`)
 **Format**: `!O010203,\r`
  Disarms all areas (1, 2, 3).
**Response**: Three Area status messages, one per area (see [Area Commands > Response]).
  
**Example Responses**:
```
\xFEA001\JOHN DOE        \HOME MODE        0\xFF
\xFEA002\JOHN DOE        \SLEEP MODE       0\xFF
\xFEA003\JOHN DOE        \AWAY MODE        0\xFF
```

 ### Query Status (`?WBxx`)
 **Format**: `?WB<AreaNumber>Y001\r`
 **Examples**:
 ```
 ?WB01Y001\r   // Query area 1
 ?WB02Y001\r   // Query area 2
 ?WB03Y001\r   // Query area 3
 ```
 **Response**: Same as Area status response.

 ## Output Control Commands

 **Format**: `!Q<OutputNumber><Command>\r`
 - `<OutputNumber>`: 3-digit string, e.g. "001", "005"
 - `<Command>`:
   - `S` = Steady On
   - `O` = Off
   - `P` = Pulse On
   - `M` = Momentary
   - `T` = Temporal Code 3
 **Examples**:
 ```
 !Q005S\r   // Turn on output 5 (steady)
 !Q007O\r   // Turn off output 7
 ```
**Response**:
 - Position 2: `Z` (Output status message)
 - Characters 3–5: Output number
 - Characters 7–22: User name (16 chars)
 - Characters 24–39: Output name (16 chars)
 - Third-from-last character: Access (1) or Denied (0)
  
**Example Responses**:
```
\xFEZ005\JANE SMITH      \LIVING ROOM      1\xFF  // Access granted
\xFEZ005\BOB            \BACK DOOR        0\xFF  // Access denied
```

 ### Query Output Status (`?WQ`)
 **Format**: `?WQ<OutputNumber>\\r`
 - `<OutputNumber>`: 3-digit string, e.g., "001", "005"
 **Example**:
 ```
 ?WQ005\\r   // Query status for output 5
 ```
 **Response**: Same as [Output Control Commands > Response].

 ## Zone Commands
### Query Zone Details (`?WB`)
**Initial Format**: `?WB**Y<StartZoneNumber>\\r`
**Continued Format**: `?WB\\r`
- `<StartZoneNumber>`: 3-digit, 001–999
Retrieves all zone definitions and statuses in multiple chunks. Send the initial command with the starting zone number (typically `001`) to receive the first block of zone records. Each response contains one or more zone records separated by ASCII 30 (`\\x1E`), ending with a dash (`-`) to indicate more records are available. After a response ending in `-`, send `?WB\\r` (no parameters) to retrieve the next block. Repeat until the panel returns `*WB-`, indicating the end of the list.
**Response Packet Format**:
- Payload begins after the `*WB` header.
- Zone records:
  - `A<AreaNumber>`: assigns subsequent zones to the specified area.
  - `L<ZoneNumber><Status><ZoneName>`: zone entry, where:
    - `<ZoneNumber>`: 3-digit ID.
    - `<Status>`: `N`=Normal, `O`=Open, `S`=Short, `X`=Bypassed, `L`=Low Battery, `M`=Missing.
    - `<ZoneName>`: up to 16 characters.
- Records are separated by `\\x1E` and the packet ends with `-`.
**Example**:
```
?WB**Y001\\r
*WBA001L001NFront Door\\x1EL002NBack Door\\x1E-
?WB\\r
*WBL003NGarage Door\\x1EL004NPatio Door\\x1E-
?WB\\r
*WB-
```

 ### Bypass Zone (`!X`)
 **Format**: `!X<ZoneNumber>\r`
 - `<ZoneNumber>`: 3-digit, 001–999
**Example**:
```
!X023\r   // Bypass zone 23
```
**Response**: Same as Reset Zone status response.
  
**Example Response**:
```
\xFEZ023\JOHN DOE        \AREA 1           \WINDOW 1        1 1\xFF
```

 ### Reset Zone (`!Y`)
 **Format**: `!Y<ZoneNumber>,\r`
 - `<ZoneNumber>`: 3-digit, 001–999
 - Comma required.
**Example**:
```
!Y023,\r   // Reset (restore) zone 23
```
 **Response**:
 - Position 2: `Z` (Zone status message)
 - Characters 3–5: Zone number
 - Characters 7–22: User name (16 chars)
 - Characters 24–39: Area name (16 chars)
 - Characters 41–56: Zone name (16 chars)
 - Second-to-last char: Message type
   - `0` = non-normal
   - `1` = bypassed
   - `2` = alarm
   - `3` = restore
   - `4` = trouble
   - `5` = fault
   - `6` = reset
   - `7` = forced
   - `8` = open
   - `9` = close
 - Last char: Zone type
  
**Notes on Zone Messages**:
- User names and zone names are transmitted as ASCII fields (characters 7–22 for user name, 41–56 for zone name).
- Numeric user codes are not included in these real-time status messages; only the programmed names are provided.
**Example Response**:
```
\xFEZ023\JOHN DOE        \AREA 1           \WINDOW 1        3 1\xFF
```
   - `0` = unknown
   - `1` = burglar
   - `2` = fire
   - `3` = generic
   - `4` = supervisory
   - `5` = panic
   - `6` = emergency
   - `7` = aux 1
   - `8` = aux 2