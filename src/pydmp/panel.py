"""High-level async panel controller."""

import asyncio
import logging
from typing import Any

from .area import Area
from .connection import DMPConnection
from .const.commands import DMPCommand
from .const.protocol import DEFAULT_PORT
from .exceptions import DMPConnectionError
from .output import Output
from .status_parser import parse_s3_message
from .const.events import DMPEventType
from .protocol import StatusResponse
from .protocol import UserCodesResponse, UserProfilesResponse, UserCode, UserProfile
from .zone import Zone

_LOGGER = logging.getLogger(__name__)


# Active connection guard: one connection per (host, port, account)
_ACTIVE_CONNECTIONS: set[tuple[str, int, str]] = set()


class DMPPanel:
    """High-level async interface to DMP panel."""

    def __init__(self, port: int = DEFAULT_PORT, timeout: float = 10.0):
        """Initialize panel.

        Args:
            port: TCP port (default: 2011)
            timeout: Connection timeout in seconds
        """
        self.port = port
        self.timeout = timeout

        self._connection: DMPConnection | None = None
        self._areas: dict[int, Area] = {}
        self._zones: dict[int, Zone] = {}
        self._outputs: dict[int, Output] = {}
        self._keepalive_task: Any | None = None
        self._keepalive_interval: float = 10.0
        # User code cache
        self._user_cache_by_code: dict[str, UserCode] = {}
        self._user_cache_by_pin: dict[str, UserCode] = {}
        self._user_cache_lock = asyncio.Lock()
        self._status_callbacks: dict[Any, Any] = {}

        _LOGGER.debug("Panel initialized")

    @property
    def is_connected(self) -> bool:
        """Check if connected to panel."""
        return self._connection is not None and self._connection.is_connected

    async def connect(
        self,
        host: str,
        account: str,
        remote_key: str,
    ) -> None:
        """Connect to panel and authenticate.

        Args:
            host: Panel IP address or hostname
            account: 5-digit account number
            remote_key: Remote key for authentication

        Raises:
            DMPConnectionError: If connection fails
        """
        if self.is_connected:
            _LOGGER.warning("Already connected")
            return

        _LOGGER.info(f"Connecting to panel at {host}:{self.port}")

        # Guard against multiple active connections to the same panel
        key = (host, self.port, account)
        if key in _ACTIVE_CONNECTIONS:
            raise DMPConnectionError(
                f"Active connection already exists for {host}:{self.port} account {account}. "
                "Only one connection is allowed."
            )

        self._connection = DMPConnection(host, account, remote_key, self.port, self.timeout)
        await self._connection.connect()

        # Register active connection
        _ACTIVE_CONNECTIONS.add(key)

        _LOGGER.info("Panel connected")

    async def disconnect(self) -> None:
        """Disconnect from panel."""
        if not self.is_connected or not self._connection:
            return

        _LOGGER.info("Disconnecting from panel")
        # Stop keep-alive loop if running
        await self.stop_keepalive()
        # Cleanup active connection guard
        try:
            if self._connection:
                key = (self._connection.host, self._connection.port, self._connection.account)
                _ACTIVE_CONNECTIONS.discard(key)
        except Exception:
            pass

        await self._connection.disconnect()
        self._connection = None

    async def update_status(self) -> None:
        """Update status of all areas and zones from panel.

        Raises:
            DMPConnectionError: If not connected or update fails
        """
        if not self.is_connected or not self._connection:
            raise DMPConnectionError("Not connected to panel")

        _LOGGER.debug("Updating panel status")

        # Request zone status (this returns both areas and zones)
        # First command: ?WB**Y001 (initial query)
        # Subsequent: ?WB (continuation)
        commands: list[tuple[str, dict[str, Any]]] = [
            (DMPCommand.GET_ZONE_STATUS.value, {"zone": "001"})
        ] + [
            (DMPCommand.GET_ZONE_STATUS_CONT.value, {})
        ] * 10

        responses: list[StatusResponse] = []
        for cmd, params in commands:
            response = await self._connection.send_command(cmd, **params)
            if isinstance(response, StatusResponse):
                responses.append(response)

        # Merge all responses
        all_areas: dict[str, Any] = {}
        all_zones: dict[str, Any] = {}

        for response in responses:
            all_areas.update(response.areas)
            all_zones.update(response.zones)

        # Update areas
        for area_num_str, area_status in all_areas.items():
            area_num = int(area_num_str)
            if area_num not in self._areas:
                self._areas[area_num] = Area(
                    self, area_num, area_status.name, area_status.state
                )
            else:
                self._areas[area_num].update_state(area_status.state, area_status.name)

        # Update zones
        for zone_num_str, zone_status in all_zones.items():
            zone_num = int(zone_num_str)
            if zone_num not in self._zones:
                self._zones[zone_num] = Zone(
                    self, zone_num, zone_status.name, state=zone_status.state
                )
            else:
                self._zones[zone_num].update_state(zone_status.state, zone_status.name)

        _LOGGER.info(
            f"Status updated: {len(self._areas)} areas, {len(self._zones)} zones"
        )

    async def get_areas(self) -> list[Area]:
        """Get all areas.

        Returns:
            List of Area objects

        Raises:
            DMPConnectionError: If not connected
        """
        if not self.is_connected:
            raise DMPConnectionError("Not connected to panel")

        if not self._areas:
            await self.update_status()

        return sorted(self._areas.values(), key=lambda a: a.number)

    async def get_area(self, number: int) -> Area:
        """Get specific area by number.

        Args:
            number: Area number (1-8)

        Returns:
            Area object

        Raises:
            DMPConnectionError: If not connected
            KeyError: If area not found
        """
        if not self.is_connected:
            raise DMPConnectionError("Not connected to panel")

        if not self._areas:
            await self.update_status()

        if number not in self._areas:
            raise KeyError(f"Area {number} not found")

        return self._areas[number]

    async def get_zones(self) -> list[Zone]:
        """Get all zones.

        Returns:
            List of Zone objects

        Raises:
            DMPConnectionError: If not connected
        """
        if not self.is_connected:
            raise DMPConnectionError("Not connected to panel")

        if not self._zones:
            await self.update_status()

        return sorted(self._zones.values(), key=lambda z: z.number)

    async def get_zone(self, number: int) -> Zone:
        """Get specific zone by number.

        Args:
            number: Zone number (1-999)

        Returns:
            Zone object

        Raises:
            DMPConnectionError: If not connected
            KeyError: If zone not found
        """
        if not self.is_connected:
            raise DMPConnectionError("Not connected to panel")

        if not self._zones:
            await self.update_status()

        if number not in self._zones:
            raise KeyError(f"Zone {number} not found")

        return self._zones[number]

    async def get_outputs(self) -> list[Output]:
        """Get all outputs.

        Note: Outputs are created on-demand as they're not returned in status queries.

        Returns:
            List of Output objects
        """
        # Create outputs 1-4 if they don't exist
        for i in range(1, 5):
            if i not in self._outputs:
                self._outputs[i] = Output(self, i, f"Output {i}")

        return sorted(self._outputs.values(), key=lambda o: o.number)

    async def get_output(self, number: int) -> Output:
        """Get specific output by number.

        Args:
            number: Output number (1-4)

        Returns:
            Output object

        Raises:
            KeyError: If output number invalid
        """
        if not 1 <= number <= 4:
            raise KeyError(f"Output number must be 1-4, got {number}")

        if number not in self._outputs:
            self._outputs[number] = Output(self, number, f"Output {number}")

        return self._outputs[number]

    async def sensor_reset(self) -> None:
        """Send sensor reset command to the panel (!E001)."""
        if not self.is_connected or not self._connection:
            raise DMPConnectionError("Not connected to panel")
        await self._connection.send_command(DMPCommand.SENSOR_RESET.value)

    async def get_user_codes(self) -> list[UserCode]:
        """Retrieve all user codes from the panel (decrypting entries)."""
        if not self.is_connected or not self._connection:
            raise DMPConnectionError("Not connected to panel")

        users: list[UserCode] = []
        start = "0000"
        max_pages = 200
        pages = 0
        while pages < max_pages:
            pages += 1
            resp = await self._connection.send_command(
                DMPCommand.GET_USER_CODES.value, user=start
            )
            if not isinstance(resp, UserCodesResponse):
                break

            users.extend(resp.users)

            # Determine continuation boundary (per Lua: last < 9999)
            if resp.has_more and resp.last_number:
                try:
                    last = int(resp.last_number)
                except ValueError:
                    break
                if last < 9999:
                    next_start = f"{last + 1:04d}"
                    # If the panel keeps returning the same page, stop
                    if next_start == start:
                        break
                    start = next_start
                    continue
            break
        return users

    async def get_user_profiles(self) -> list[UserProfile]:
        """Retrieve all user profiles from the panel."""
        if not self.is_connected or not self._connection:
            raise DMPConnectionError("Not connected to panel")

        profiles: list[UserProfile] = []
        start = "000"
        max_pages = 50
        pages = 0
        while pages < max_pages:
            pages += 1
            resp = await self._connection.send_command(
                DMPCommand.GET_USER_PROFILES.value, profile=start
            )
            if not isinstance(resp, UserProfilesResponse):
                break

            profiles.extend(resp.profiles)

            if resp.has_more and resp.last_number:
                try:
                    last = int(resp.last_number)
                except ValueError:
                    break
                if last < 99:
                    next_start = f"{last + 1:03d}"
                    if next_start == start:
                        break
                    start = next_start
                    continue
            break
        return profiles

    async def _refresh_user_cache(self) -> None:
        """Refresh internal user code cache from panel."""
        async with self._user_cache_lock:
            users = await self.get_user_codes()
            self._user_cache_by_code = {}
            self._user_cache_by_pin = {}
            for u in users:
                code = (u.code or "").strip()
                pin = (u.pin or "").strip()
                if code:
                    self._user_cache_by_code[code] = u
                if pin:
                    self._user_cache_by_pin[pin] = u

    async def check_code(self, code: str, *, include_pin: bool = True, refresh_if_missing: bool = True) -> UserCode | None:
        """Check if a user code (or PIN) exists in the panel.

        Args:
            code: The code/PIN string to validate
            include_pin: If True, also match against PIN codes
            refresh_if_missing: If True, refresh cache on miss and retry once

        Returns:
            Matching UserCode or None if not found
        """
        # Ensure cache is loaded at least once
        if not (self._user_cache_by_code or self._user_cache_by_pin):
            try:
                await self._refresh_user_cache()
            except Exception as e:
                _LOGGER.debug("Initial user cache refresh failed: %s", e)

        # First attempt
        user = self._user_cache_by_code.get(code)
        if not user and include_pin:
            user = self._user_cache_by_pin.get(code)
        if user or not refresh_if_missing:
            return user

        # Refresh and retry once
        try:
            await self._refresh_user_cache()
        except Exception as e:
            _LOGGER.debug("User cache refresh on miss failed: %s", e)
            return None

        user = self._user_cache_by_code.get(code)
        if not user and include_pin:
            user = self._user_cache_by_pin.get(code)
        return user

    def attach_status_server(self, server: Any) -> None:
        """Attach a DMPStatusServer to auto-refresh user cache on Zu events.

        When the server receives a User Codes (Zu) event, the panel will refresh
        its user cache in the background. Call detach_status_server to remove.
        """

        if server in self._status_callbacks:
            return

        async def _on_event(msg: Any) -> None:
            try:
                evt = parse_s3_message(msg)
                if evt.category is DMPEventType.USER_CODES:
                    await self._refresh_user_cache()
            except Exception as e:
                _LOGGER.debug("Status server callback error: %s", e)

        self._status_callbacks[server] = _on_event
        try:
            server.register_callback(_on_event)
        except Exception as e:
            _LOGGER.debug("Failed to register status callback: %s", e)

    def detach_status_server(self, server: Any) -> None:
        """Detach a previously attached DMPStatusServer."""
        cb = self._status_callbacks.pop(server, None)
        if cb is None:
            return
        try:
            server.remove_callback(cb)
        except Exception:
            pass

    async def start_keepalive(self, interval: float = 10.0) -> None:
        """Start periodic keep-alive (!H) while connected.

        Args:
            interval: Seconds between keep-alive messages (default: 10)
        """
        if not self.is_connected or not self._connection:
            raise DMPConnectionError("Not connected to panel")

        await self.stop_keepalive()
        self._keepalive_interval = max(1.0, float(interval))

        async def _loop() -> None:
            _LOGGER.debug("Keep-alive loop started (%.1fs)", self._keepalive_interval)
            try:
                while self.is_connected and self._connection:
                    try:
                        await self._connection.keep_alive()
                    except Exception as e:
                        _LOGGER.debug("Keep-alive send failed: %s", e)
                    await asyncio.sleep(self._keepalive_interval)
            finally:
                _LOGGER.debug("Keep-alive loop stopped")

        # Create background task
        self._keepalive_task = asyncio.create_task(_loop())

    async def stop_keepalive(self) -> None:
        """Stop periodic keep-alive if running."""
        task = self._keepalive_task
        self._keepalive_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    async def arm_areas(
        self,
        area_numbers: list[int] | tuple[int, ...],
        bypass_faulted: bool = False,
        force_arm: bool = False,
        instant: bool | None = None,
    ) -> None:
        """Arm one or more areas in a single command.

        Concatenates two-digit area numbers per DMP format and sends
        !C{areas},{bypass}{force}.
        """
        if not self.is_connected or not self._connection:
            raise DMPConnectionError("Not connected to panel")
        if not area_numbers:
            raise ValueError("area_numbers must not be empty")
        for n in area_numbers:
            if not 0 <= int(n) <= 99:
                raise ValueError(f"Invalid area number: {n}")

        areas_concat = "".join(f"{int(n):02d}" for n in area_numbers)
        bypass = "Y" if bypass_faulted else "N"
        force = "Y" if force_arm else "N"
        instant_flag = "Y" if instant is True else ("N" if instant is False else "")

        resp = await self._connection.send_command(
            DMPCommand.ARM.value,
            area=areas_concat,
            bypass=bypass,
            force=force,
            instant=instant_flag,
        )
        if resp == "NAK":
            raise DMPConnectionError("Panel rejected arm command")

    async def disarm_areas(self, area_numbers: list[int] | tuple[int, ...]) -> None:
        """Disarm one or more areas in a single command: !O{areas}."""
        if not self.is_connected or not self._connection:
            raise DMPConnectionError("Not connected to panel")
        if not area_numbers:
            raise ValueError("area_numbers must not be empty")
        for n in area_numbers:
            if not 0 <= int(n) <= 99:
                raise ValueError(f"Invalid area number: {n}")

        areas_concat = "".join(f"{int(n):02d}" for n in area_numbers)
        resp = await self._connection.send_command(DMPCommand.DISARM.value, area=areas_concat)
        if resp == "NAK":
            raise DMPConnectionError("Panel rejected disarm command")

    async def __aenter__(self) -> "DMPPanel":
        """Async context manager entry."""
        # Panel is created unconnected, user must call connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()

    def __repr__(self) -> str:
        """String representation."""
        status = "connected" if self.is_connected else "disconnected"
        return f"<DMPPanel {status}, {len(self._areas)} areas, {len(self._zones)} zones>"
