"""Thin stateless client helpers built on top of the core manager."""

from __future__ import annotations

from collections.abc import Callable

from .area_control import (
    AreaControlReply,
    TransactionArmAreas,
    TransactionDisarmAreas,
)
from .area_status import (
    AreaStatusReply,
    TransactionQueryAreas,
)
from .lockout_code import LockoutCodeReply, TransactionQueryLockoutCode
from .manager import CommandSessionManager
from .models import PanelEndpoint
from .profiles import ProfileReply, TransactionQueryProfiles
from .sensor_reset import SensorResetReply, TransactionSensorReset
from .sessions import SessionProfile, SessionProfileBlankV2
from .transport import PanelTransport, TransportProtocol
from .users import TransactionQueryUsers, UserReply
from .zone_control import (
    TransactionBypassZone,
    TransactionUnbypassZone,
    ZoneControlReply,
)
from .zone_status import TransactionQueryZones, ZoneStatusReply


class CorePanelClient:
    """Stateless command client built on top of `CommandSessionManager`."""

    def __init__(
        self,
        endpoint: PanelEndpoint,
        *,
        session_profile: SessionProfile | None = None,
        transport_factory: Callable[[PanelEndpoint], TransportProtocol] | None = None,
    ) -> None:
        self._manager = CommandSessionManager(
            endpoint=endpoint,
            session_profile=session_profile or SessionProfileBlankV2(),
            transport_factory=transport_factory or PanelTransport,
        )

    @property
    def manager(self) -> CommandSessionManager:
        """Expose the manager for advanced callers."""
        return self._manager

    async def close(self) -> None:
        """Close the underlying manager."""
        await self._manager.close()

    async def query_wa(self, area: int | str = 1) -> AreaStatusReply:
        """Run a full `?WA` transaction and return the parsed reply."""
        transaction = await self._manager.submit(TransactionQueryAreas(area))
        parsed = transaction.parsed_response
        if not isinstance(parsed, AreaStatusReply):
            raise ValueError("Query completed without a parsed WA reply")
        return parsed

    async def arm_areas(
        self,
        areas,
        *,
        bypass_faulted: bool = True,
        force_arm: bool = False,
        instant: bool = False,
    ) -> AreaControlReply:
        """Run `!C` for one or more areas and return the parsed reply."""
        transaction = await self._manager.submit(
            TransactionArmAreas(
                areas,
                bypass_faulted=bypass_faulted,
                force_arm=force_arm,
                instant=instant,
            )
        )
        parsed = transaction.parsed_response
        if not isinstance(parsed, AreaControlReply):
            raise ValueError("Command completed without a parsed C reply")
        return parsed

    async def disarm_areas(self, areas) -> AreaControlReply:
        """Run `!O` for one or more areas and return the parsed reply."""
        transaction = await self._manager.submit(TransactionDisarmAreas(areas))
        parsed = transaction.parsed_response
        if not isinstance(parsed, AreaControlReply):
            raise ValueError("Command completed without a parsed O reply")
        return parsed

    async def query_zones(self) -> ZoneStatusReply:
        """Run a full `?WB` zone snapshot transaction and return the parsed reply."""
        transaction = await self._manager.submit(TransactionQueryZones())
        parsed = transaction.parsed_response
        if not isinstance(parsed, ZoneStatusReply):
            raise ValueError("Query completed without a parsed WB reply")
        return parsed

    async def query_lockout_code(self) -> LockoutCodeReply:
        """Run a `?ZZ` lockout-code query and return the parsed reply."""
        transaction = await self._manager.submit(TransactionQueryLockoutCode())
        parsed = transaction.parsed_response
        if not isinstance(parsed, LockoutCodeReply):
            raise ValueError("Query completed without a parsed ZZ reply")
        return parsed

    async def query_users(self) -> UserReply:
        """Run a full `?P=` user-table transaction and return the parsed reply."""
        transaction = await self._manager.submit(TransactionQueryUsers())
        parsed = transaction.parsed_response
        if not isinstance(parsed, UserReply):
            raise ValueError("Query completed without a parsed P= reply")
        return parsed

    async def query_profiles(self) -> ProfileReply:
        """Run a full `?U` profile-table transaction and return the parsed reply."""
        transaction = await self._manager.submit(TransactionQueryProfiles())
        parsed = transaction.parsed_response
        if not isinstance(parsed, ProfileReply):
            raise ValueError("Query completed without a parsed U reply")
        return parsed

    async def sensor_reset(self) -> SensorResetReply:
        """Run `!E001` and return the parsed reply."""
        transaction = await self._manager.submit(TransactionSensorReset())
        parsed = transaction.parsed_response
        if not isinstance(parsed, SensorResetReply):
            raise ValueError("Command completed without a parsed E reply")
        return parsed

    async def bypass_zone(self, zone: int | str) -> ZoneControlReply:
        """Run `!X` for one zone and return the parsed reply."""
        transaction = await self._manager.submit(TransactionBypassZone(zone))
        parsed = transaction.parsed_response
        if not isinstance(parsed, ZoneControlReply):
            raise ValueError("Command completed without a parsed X reply")
        return parsed

    async def unbypass_zone(self, zone: int | str) -> ZoneControlReply:
        """Run `!Y` for one zone and return the parsed reply."""
        transaction = await self._manager.submit(TransactionUnbypassZone(zone))
        parsed = transaction.parsed_response
        if not isinstance(parsed, ZoneControlReply):
            raise ValueError("Command completed without a parsed Y reply")
        return parsed
