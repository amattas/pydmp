"""High-level compatibility panel built on top of the new core.

This wrapper is the migration bridge between the older stateful `pydmp`
surface and the newer transaction-based core.

The wrapper keeps a few old seams alive on purpose:

- `_send_command`
- `_connection`
- `_protocol`
- `_ACTIVE_CONNECTIONS`

Those seams matter because older tests and older application code often patch
or inspect them directly. Normal wrapper use still prefers the new core.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

from ..const.commands import DMPCommand
from ..const.events import DMPEventType, DMPRealTimeStatusEvent
from ..const.protocol import DEFAULT_PORT, RATE_LIMIT_SECONDS
from ..core import (
    CorePanelClient,
    PanelEndpoint,
    SessionProfileBlankV2,
    SessionProfileKeyedV2,
    reply_optional,
)
from ..exceptions import (
    DMPCommandError,
    DMPConnectionError,
    DMPInvalidParameterError,
)
from ..profile import UserProfile
from ..protocol import (
    OutputsResponse,
    StatusResponse,
    UserCode,
    UserCodesResponse,
    UserProfilesResponse,
)
from ..status_parser import parse_s3_message
from ._compat import (
    WRAPPER_IDLE_DISCONNECT_SECONDS,
    build_user_code,
    build_user_profile,
    map_area_state,
    map_core_error,
    map_output_state,
    status_message_definition,
)
from .area import Area
from .output import Output
from .zone import Zone

_LOGGER = logging.getLogger(__name__)

# Match the old one-live-connection-per-panel behavior.
_ACTIVE_CONNECTIONS: set[tuple[str, int, str]] = set()


def _build_core_client(endpoint: PanelEndpoint, session_profile) -> CorePanelClient:
    """Create one new-core client.

    This helper stays tiny so tests can patch it with a fake client.
    """
    return CorePanelClient(endpoint, session_profile=session_profile)


async def _close_client_quietly(client: CorePanelClient | None) -> None:
    """Close a new-core client without letting shutdown noise hide real errors."""
    if client is None:
        return

    try:
        await client.close()
    except Exception:
        _LOGGER.debug("Ignoring client close failure during wrapper cleanup", exc_info=True)


class DMPPanel:
    """Compatibility async panel with an old-style stateful surface."""

    def __init__(self, port: int = DEFAULT_PORT, timeout: float = 10.0) -> None:
        self.port = port
        self.timeout = timeout

        # New-core path.
        self._client: CorePanelClient | None = None
        self._connected = False

        # Legacy seams kept for migration and tests.
        self._connection: Any | None = None
        self._protocol: Any | None = None
        self._active_key: tuple[str, int, str] | None = None

        # Cached high-level objects.
        self._areas: dict[int, Area] = {}
        self._zones: dict[int, Zone] = {}
        self._outputs: dict[int, Output] = {}

        # Background keepalive.
        self._keepalive_task: asyncio.Task[None] | None = None
        self._keepalive_interval = 10.0

        # Cached user lookups used by `check_code()`.
        self._user_cache_by_code: dict[str, UserCode] = {}
        self._user_cache_by_pin: dict[str, UserCode] = {}
        self._user_cache_lock = asyncio.Lock()

        # Status-server callback bookkeeping.
        self._status_callbacks: dict[Any, Any] = {}

    @property
    def is_connected(self) -> bool:
        """Return True when the wrapper has a usable command path."""
        if self._connected:
            return True

        if self._connection is None:
            return False

        return bool(getattr(self._connection, "is_connected", False))

    async def connect(self, host: str, account: str, remote_key: str) -> None:
        """Open one wrapper session.

        A remote key that is empty or only spaces is treated as blank V2.
        That detail matters because some existing integrations store blank keys
        as a fixed-width space-filled string.
        """
        if self.is_connected:
            return

        key = (str(host), int(self.port), str(account))
        if key in _ACTIVE_CONNECTIONS:
            raise DMPConnectionError(
                f"Active connection already exists for {host}:{self.port} account {account}."
            )

        key_text = str(remote_key or "")
        use_blank_v2 = key_text.strip() == ""
        endpoint = PanelEndpoint(
            host=host,
            account=account,
            port=self.port,
            remote_key=None if use_blank_v2 else key_text,
            connect_timeout=self.timeout,
            idle_disconnect_seconds=WRAPPER_IDLE_DISCONNECT_SECONDS,
            rate_limit_seconds=RATE_LIMIT_SECONDS,
        )
        session_profile = SessionProfileBlankV2() if use_blank_v2 else SessionProfileKeyedV2(key_text)
        client = _build_core_client(endpoint, session_profile)

        try:
            area_reply = await client.query_areas()
        except Exception as error:
            await _close_client_quietly(client)
            raise map_core_error(error, context="Failed to connect to panel") from error

        self._client = client
        self._connected = True
        self._active_key = key
        _ACTIVE_CONNECTIONS.add(key)
        self._refresh_area_cache(area_reply.areas)

    async def disconnect(self) -> None:
        """Close any active session and stop background tasks."""
        await self.stop_keepalive()

        try:
            if self._connection is not None and self._protocol is not None and hasattr(self._connection, "send_and_receive"):
                command = self._protocol.encode_command(DMPCommand.DISCONNECT.value)
                await self._connection.send_and_receive(command)
        except Exception:
            _LOGGER.debug("Ignoring legacy disconnect send failure", exc_info=True)

        try:
            if self._connection is not None and hasattr(self._connection, "disconnect"):
                await self._connection.disconnect()
        except Exception:
            _LOGGER.debug("Ignoring legacy transport disconnect failure", exc_info=True)

        await _close_client_quietly(self._client)

        if self._active_key is not None:
            _ACTIVE_CONNECTIONS.discard(self._active_key)

        self._client = None
        self._connected = False
        self._connection = None
        self._protocol = None
        self._active_key = None

    async def update_status(self) -> None:
        """Refresh the area and zone caches."""
        if self._use_direct_core_path():
            client = self._require_client()
            try:
                area_reply = await client.query_areas()
                zone_reply = await client.query_zones()
            except Exception as error:
                raise map_core_error(error, context="Failed to update panel status") from error

            self._refresh_area_cache(area_reply.areas)
            self._refresh_zone_cache(zone_reply.zones)
            return

        self._require_connected()

        responses: list[StatusResponse] = []
        commands = [(DMPCommand.GET_ZONE_STATUS.value, {"zone": "001"})] + [(DMPCommand.GET_ZONE_STATUS_CONT.value, {})] * 10
        for command, kwargs in commands:
            response = await self._send_command(command, **kwargs)
            if isinstance(response, StatusResponse):
                responses.append(response)

        merged_areas: dict[str, Any] = {}
        merged_zones: dict[str, Any] = {}
        for response in responses:
            merged_areas.update(response.areas)
            merged_zones.update(response.zones)

        self._refresh_area_cache(merged_areas.values())
        self._refresh_zone_cache(merged_zones.values())

    async def get_areas(self) -> list[Area]:
        """Return all known areas, loading them if needed."""
        self._require_connected()
        if not self._areas:
            await self.update_status()
        return sorted(self._areas.values(), key=lambda area: area.number)

    async def get_area(self, number: int) -> Area:
        """Return one area by number."""
        self._require_connected()
        if not self._areas:
            await self.update_status()
        if number not in self._areas:
            raise KeyError(f"Area {number} not found")
        return self._areas[number]

    async def get_zones(self) -> list[Zone]:
        """Return all known zones, loading them if needed."""
        self._require_connected()
        if not self._zones:
            await self.update_status()
        return sorted(self._zones.values(), key=lambda zone: zone.number)

    async def get_zone(self, number: int) -> Zone:
        """Return one zone by number."""
        self._require_connected()
        if not self._zones:
            await self.update_status()
        if number not in self._zones:
            raise KeyError(f"Zone {number} not found")
        return self._zones[number]

    async def get_outputs(self) -> list[Output]:
        """Return outputs known to the wrapper.

        The old high-level API created outputs 1..4 even before talking to the
        panel. We keep that convenience.
        """
        self._ensure_default_outputs()
        return sorted(self._outputs.values(), key=lambda output: output.number)

    async def get_output(self, number: int) -> Output:
        """Return one output by number."""
        if not 1 <= int(number) <= 999:
            raise KeyError(f"Output number must be 1-999, got {number}")

        self._ensure_default_outputs()
        if number not in self._outputs:
            self._outputs[number] = Output(self, int(number), f"Output {int(number)}")
        return self._outputs[number]

    async def update_output_status(self) -> None:
        """Refresh visible numeric outputs from the panel."""
        if self._use_direct_core_path():
            client = self._require_client()
            try:
                reply = await client.query_outputs(namespace="numeric", named_only=False)
            except Exception as error:
                raise map_core_error(error, context="Failed to update output status") from error

            self._refresh_output_cache(reply.records)
            return

        self._require_connected()

        merged_outputs: dict[str, Any] = {}
        commands = [(DMPCommand.GET_OUTPUT_STATUS.value, {"output": "001"})] + [(DMPCommand.GET_OUTPUT_STATUS_CONT.value, {})] * 5
        for command, kwargs in commands:
            response = await self._send_command(command, **kwargs)
            if isinstance(response, OutputsResponse):
                merged_outputs.update(response.outputs)

        self._refresh_output_cache(merged_outputs.values())

    async def sensor_reset(self) -> None:
        """Send the standard sensor-reset command."""
        self._require_connected()
        response = await self._send_command(DMPCommand.SENSOR_RESET.value)
        if response == "NAK":
            raise DMPCommandError("Panel rejected sensor reset command")

    async def get_user_codes(self) -> list[UserCode]:
        """Return the visible user table and refresh the code cache."""
        if self._use_direct_core_path():
            client = self._require_client()
            try:
                reply = await client.query_users()
            except Exception as error:
                raise map_core_error(error, context="Failed to query user codes") from error

            users = [build_user_code(record) for record in reply.users]
            self._store_user_caches(users)
            return users

        self._require_connected()

        users: list[UserCode] = []
        selector = "0000"
        seen_selectors: set[str] = set()

        while selector not in seen_selectors:
            seen_selectors.add(selector)
            response = await self._send_command(DMPCommand.GET_USER_CODES.value, user=selector)
            if not isinstance(response, UserCodesResponse):
                break

            users.extend(response.users)
            if not response.has_more or not response.last_number:
                break

            next_selector = f"{min(int(response.last_number) + 1, 9999):04d}"
            if next_selector == selector:
                break
            selector = next_selector

        self._store_user_caches(users)
        return users

    async def get_user_profiles(self) -> list[UserProfile]:
        """Return the visible profile table."""
        if self._use_direct_core_path():
            client = self._require_client()
            try:
                reply = await client.query_profiles()
            except Exception as error:
                raise map_core_error(error, context="Failed to query user profiles") from error

            return [build_user_profile(record) for record in reply.profiles]

        self._require_connected()

        profiles: list[UserProfile] = []
        selector = "000"
        seen_selectors: set[str] = set()

        while selector not in seen_selectors:
            seen_selectors.add(selector)
            response = await self._send_command(DMPCommand.GET_USER_PROFILES.value, profile=selector)
            if not isinstance(response, UserProfilesResponse):
                break

            profiles.extend(response.profiles)
            if not response.has_more or not response.last_number:
                break

            next_selector = f"{min(int(response.last_number) + 1, 999):03d}"
            if next_selector == selector:
                break
            selector = next_selector

        return profiles

    async def check_code(
        self,
        code: str,
        *,
        include_pin: bool = True,
        refresh_if_missing: bool = True,
    ) -> UserCode | None:
        """Look up one code in the cached user table."""
        async with self._user_cache_lock:
            found = self._user_cache_by_code.get(code)
            if found is not None:
                return found

            if include_pin:
                found = self._user_cache_by_pin.get(code)
                if found is not None:
                    return found

            if not refresh_if_missing:
                return None

            try:
                await self._refresh_user_cache()
            except Exception:
                _LOGGER.debug("User cache refresh failed during check_code", exc_info=True)
                return None

            found = self._user_cache_by_code.get(code)
            if found is not None:
                return found
            if include_pin:
                return self._user_cache_by_pin.get(code)
            return None

    def attach_status_server(self, server: Any) -> None:
        """Attach one status-server style callback source."""
        if server in self._status_callbacks:
            return

        async def _callback(message: Any) -> None:
            parsed = None
            try:
                parsed = parse_s3_message(message)
            except Exception:
                parsed = None

            is_user_code_event = False
            if parsed is not None and getattr(parsed, "category", None) is DMPEventType.USER_CODES:
                is_user_code_event = True
            elif status_message_definition(message) == "Zu":
                is_user_code_event = True

            if not is_user_code_event:
                return

            try:
                await self._refresh_user_cache()
            except Exception:
                _LOGGER.debug("User cache refresh failed for pushed event", exc_info=True)

        server.register_callback(_callback)
        self._status_callbacks[server] = _callback

    def detach_status_server(self, server: Any) -> None:
        """Detach one previously-attached status server."""
        callback = self._status_callbacks.pop(server, None)
        if callback is None:
            return
        try:
            server.remove_callback(callback)
        except Exception:
            _LOGGER.debug("Ignoring status-server detach failure", exc_info=True)

    async def start_keepalive(self, interval: float = 10.0) -> None:
        """Start a light background keepalive loop."""
        self._require_connected()

        if interval <= 0:
            raise DMPInvalidParameterError("Keepalive interval must be positive")

        self._keepalive_interval = float(interval)
        await self.stop_keepalive()

        async def _runner() -> None:
            while True:
                try:
                    if self._protocol is not None and self._connection is not None and hasattr(self._connection, "send_and_receive"):
                        command = self._protocol.encode_command(DMPCommand.KEEP_ALIVE.value)
                        await self._connection.send_and_receive(command)
                    elif self._connection is not None and hasattr(self._connection, "keep_alive"):
                        await self._connection.keep_alive()
                    elif self._use_direct_core_path():
                        client = self._require_client()
                        await client.manager.execute(DMPCommand.KEEP_ALIVE.value, completion=reply_optional(), label="keepalive")
                    else:
                        return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    _LOGGER.debug("Ignoring keepalive failure", exc_info=True)

                await asyncio.sleep(self._keepalive_interval)

        self._keepalive_task = asyncio.create_task(_runner())

    async def stop_keepalive(self) -> None:
        """Stop the background keepalive loop."""
        if self._keepalive_task is None:
            return

        task = self._keepalive_task
        self._keepalive_task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def arm_areas(
        self,
        area_numbers: list[int] | tuple[int, ...],
        *,
        bypass_faulted: bool = False,
        force_arm: bool = False,
        instant: bool | None = None,
    ) -> None:
        """Send one old-style arm command covering one or more areas."""
        self._require_connected()
        normalized = self._normalize_area_numbers(area_numbers)
        response = await self._send_command(
            DMPCommand.ARM.value,
            area="".join(f"{number:02d}" for number in normalized),
            bypass="Y" if bypass_faulted else "N",
            force="Y" if force_arm else "N",
            instant="Y" if instant is True else ("N" if instant is False else ""),
        )
        if response == "NAK":
            raise DMPConnectionError("Panel rejected arm command")

    async def disarm_areas(self, area_numbers: list[int] | tuple[int, ...]) -> None:
        """Send one old-style disarm command covering one or more areas."""
        self._require_connected()
        normalized = self._normalize_area_numbers(area_numbers)
        response = await self._send_command(
            DMPCommand.DISARM.value,
            area="".join(f"{number:02d}" for number in normalized),
        )
        if response == "NAK":
            raise DMPConnectionError("Panel rejected disarm command")

    async def bypass_zone(self, zone: int) -> None:
        """Send one zone bypass command."""
        self._require_connected()
        number = self._normalize_zone_number(zone)
        response = await self._send_command(DMPCommand.BYPASS_ZONE.value, zone=f"{number:03d}")
        if response == "NAK":
            raise DMPConnectionError("Panel rejected zone bypass command")

    async def restore_zone(self, zone: int) -> None:
        """Send one zone restore command."""
        self._require_connected()
        number = self._normalize_zone_number(zone)
        response = await self._send_command(DMPCommand.RESTORE_ZONE.value, zone=f"{number:03d}")
        if response == "NAK":
            raise DMPConnectionError("Panel rejected zone restore command")

    async def _set_output_mode(self, number: int, mode: str) -> None:
        """Set one output mode and update the local optimistic cache."""
        self._require_connected()
        if not 1 <= int(number) <= 999:
            raise DMPInvalidParameterError("Output number must be between 1 and 999")

        response = await self._send_command(
            DMPCommand.OUTPUT.value,
            output=f"{int(number):03d}",
            mode=str(mode),
        )
        if response == "NAK":
            raise DMPCommandError(f"Panel rejected output mode {mode} for output {number}")

        output = await self.get_output(int(number))
        output.update_state(self._command_mode_to_output_state(mode))

    async def _send_command(self, command: str, **kwargs: Any) -> Any:
        """Send one command through either an injected seam or the new core."""
        if self._connection is not None and hasattr(self._connection, "send_command"):
            return await self._connection.send_command(command, **kwargs)

        client = self._require_client()

        try:
            if command == DMPCommand.ARM.value:
                areas = [int(kwargs["area"][index : index + 2]) for index in range(0, len(kwargs["area"]), 2)]
                reply = await client.arm_areas(
                    areas,
                    bypass_faulted=kwargs.get("bypass") == "Y",
                    force_arm=kwargs.get("force") == "Y",
                    instant=kwargs.get("instant") == "Y",
                )
                self._set_last_nak_detail(reply.detail)
                return "ACK" if reply.acknowledged else "NAK"

            if command == DMPCommand.DISARM.value:
                areas = [int(kwargs["area"][index : index + 2]) for index in range(0, len(kwargs["area"]), 2)]
                reply = await client.disarm_areas(areas)
                self._set_last_nak_detail(reply.detail)
                return "ACK" if reply.acknowledged else "NAK"

            if command == DMPCommand.BYPASS_ZONE.value:
                reply = await client.bypass_zone(kwargs["zone"])
                self._set_last_nak_detail(reply.detail)
                return "ACK" if reply.acknowledged else "NAK"

            if command == DMPCommand.RESTORE_ZONE.value:
                reply = await client.unbypass_zone(kwargs["zone"])
                self._set_last_nak_detail(reply.detail)
                return "ACK" if reply.acknowledged else "NAK"

            if command == DMPCommand.OUTPUT.value:
                reply = await client.set_output(kwargs["output"], kwargs["mode"])
                self._set_last_nak_detail(reply.detail)
                return "ACK" if reply.acknowledged else "NAK"

            if command == DMPCommand.SENSOR_RESET.value:
                reply = await client.sensor_reset()
                self._set_last_nak_detail(reply.detail)
                return "ACK" if reply.acknowledged else "NAK"

            if command == DMPCommand.KEEP_ALIVE.value:
                await client.manager.execute(DMPCommand.KEEP_ALIVE.value, completion=reply_optional(), label="keepalive")
                return None
        except Exception as error:
            raise map_core_error(error, context=f"Failed command {command}") from error

        raise DMPCommandError(f"Wrapper does not support raw command {command}")

    async def _refresh_user_cache(self) -> None:
        """Refresh the cached code lookup tables from the panel."""
        users = await self.get_user_codes()
        self._store_user_caches(users)

    def _store_user_caches(self, users: list[UserCode]) -> None:
        """Replace both user lookup dictionaries in one place."""
        self._user_cache_by_code = {user.code: user for user in users if user.code}
        self._user_cache_by_pin = {user.pin: user for user in users if getattr(user, "pin", "")}

    def _refresh_area_cache(self, records) -> None:
        """Merge area-like records into cached `Area` objects."""
        for record in records:
            number = int(record.number)
            state = map_area_state(getattr(record, "state", "unknown"))
            name = getattr(record, "name", "")
            if number not in self._areas:
                self._areas[number] = Area(self, number, name=name, state=state)
            else:
                self._areas[number].update_state(state, name)

    def _refresh_zone_cache(self, records) -> None:
        """Merge zone-like records into cached `Zone` objects."""
        for record in records:
            number = int(record.number)
            state = getattr(record, "status", getattr(record, "state", "unknown"))
            name = getattr(record, "name", "")
            if number not in self._zones:
                self._zones[number] = Zone(self, number, name=name, state=state)
            else:
                self._zones[number].update_state(state, name)

    def _ensure_default_outputs(self) -> None:
        """Create the old convenience outputs 1..4 if needed."""
        for number in range(1, 5):
            if number not in self._outputs:
                self._outputs[number] = Output(
                    self,
                    number,
                    f"Output {number}",
                    state=DMPRealTimeStatusEvent.OUTPUT_OFF.value,
                )

    def _refresh_output_cache(self, records) -> None:
        """Merge output-like records into cached `Output` objects."""
        self._ensure_default_outputs()
        for record in records:
            number = int(record.number)
            name = getattr(record, "name", "")
            mode = getattr(record, "status", getattr(record, "mode", ""))
            state = map_output_state(mode)
            if number not in self._outputs:
                self._outputs[number] = Output(self, number, name=name, state=state)
            else:
                self._outputs[number].update_state(state, name)

    def _require_connected(self) -> None:
        """Raise the old public connection error when no command path exists."""
        if not self.is_connected:
            raise DMPConnectionError("Not connected to panel")

    def _require_client(self) -> CorePanelClient:
        """Return the live new-core client or raise a connection-style error."""
        if self._client is None:
            raise DMPConnectionError("Wrapper panel does not have an active core client")
        return self._client

    def _use_direct_core_path(self) -> bool:
        """Return True when the wrapper should use the normal new-core path."""
        return self._client is not None and self._connection is None

    def _normalize_area_numbers(self, area_numbers: list[int] | tuple[int, ...]) -> list[int]:
        """Validate and normalize an old-style area list."""
        normalized = [int(number) for number in area_numbers]
        if not normalized:
            raise ValueError("At least one area number is required")
        if any(number < 1 or number > 99 for number in normalized):
            raise ValueError("Area number must be between 1 and 99")
        return normalized

    def _normalize_zone_number(self, zone: int) -> int:
        """Validate and normalize one zone number."""
        number = int(zone)
        if not 1 <= number <= 999:
            raise DMPInvalidParameterError("Zone number must be between 1 and 999")
        return number

    def _command_mode_to_output_state(self, mode: str) -> str:
        """Map one sent output mode to the old optimistic local state."""
        text = str(mode)
        if text == "O":
            return DMPRealTimeStatusEvent.OUTPUT_OFF.value
        if text == "P":
            return DMPRealTimeStatusEvent.OUTPUT_PULSE.value
        if text == "S":
            return DMPRealTimeStatusEvent.OUTPUT_ON.value
        if text == "M":
            return DMPRealTimeStatusEvent.OUTPUT_ON.value
        return map_output_state(text)

    def _set_last_nak_detail(self, detail: str | None) -> None:
        """Store one deny/detail code on the old `_protocol.last_nak_detail` seam.

        Older code sometimes looks for a short reject detail such as `XU`.
        The new core already parses those details, so the wrapper mirrors them
        onto the old location when it is safe to do so.
        """
        if self._protocol is None:
            self._protocol = SimpleNamespace(last_nak_detail=detail)
            return

        try:
            self._protocol.last_nak_detail = detail
        except Exception:
            _LOGGER.debug("Ignoring failure while updating wrapper last_nak_detail", exc_info=True)

    def __repr__(self) -> str:
        return f"<WrapperDMPPanel connected={self.is_connected} areas={len(self._areas)} zones={len(self._zones)} outputs={len(self._outputs)}>"
