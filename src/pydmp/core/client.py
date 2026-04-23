"""Friendly async helpers built on top of the stateless core.

`CorePanelClient` is meant to be the easiest new-core entry point to read and
use directly. It does not cache panel state and it does not try to hide the
fact that every helper below is just a named transaction.

That design is intentional:

- the command/session details stay in `CommandSessionManager`
- each protocol family stays in its own transaction module
- this file gives beginners a short list of "do the obvious thing" helpers

If you want lower-level control, use `CommandSessionManager` directly.
If you want a future high-level stateful facade, it should sit above this file.
"""

from __future__ import annotations

from collections.abc import Callable

from .area_control import (
    AreaControlReply,
    TransactionArmAreas,
    TransactionDisarmAreas,
)
from .area_settings import AreaSettingsReply, TransactionQueryAreaSettings
from .area_status import (
    AreaStatusReply,
    TransactionQueryAreas,
)
from .lockout_code import LockoutCodeReply, TransactionQueryLockoutCode
from .manager import CommandSessionManager
from .models import PanelEndpoint
from .output_control import OutputControlReply, TransactionSetOutput
from .output_control import OutputControlMode
from .output_status import OutputStatusReply, TransactionQueryOutputs
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
from .zone_settings import TransactionQueryZoneSettings, ZoneSettingsReply


class CorePanelClient:
    """Simple async client that exposes one method per common transaction.

    This class is intentionally small. It gives callers a clean place to start
    without forcing them to learn the full transaction API on day one.
    """

    def __init__(
        self,
        endpoint: PanelEndpoint,
        *,
        session_profile: SessionProfile | None = None,
        transport_factory: Callable[[PanelEndpoint], TransportProtocol] | None = None,
    ) -> None:
        # Default to the blank local V2 session because that is still the most
        # common bench and lab starting point in this repo.
        self._manager = CommandSessionManager(endpoint=endpoint, session_profile=session_profile or SessionProfileBlankV2(), transport_factory=transport_factory or PanelTransport)

    @property
    def manager(self) -> CommandSessionManager:
        """Expose the underlying manager for callers who need more control.

        Most application code should stay on the named helpers below.
        This property exists for advanced scripts that want to submit custom
        transactions or inspect raw wire exchanges.
        """
        return self._manager

    async def close(self) -> None:
        """Close the current command session and underlying transport."""
        await self._manager.close()

    async def query_areas(self) -> AreaStatusReply:
        """Return the authoritative area snapshot from `?WA`.

        The project notes and captures show that `?WA` is the right source for
        full area state. We keep this helper explicit instead of hiding it
        behind a generic "status" call.
        """
        transaction = await self._manager.submit(TransactionQueryAreas())
        parsed = transaction.parsed_response
        if not isinstance(parsed, AreaStatusReply):
            raise ValueError("Query completed without a parsed WA reply")
        return parsed

    async def arm_areas(
        self,
        areas,
        *,
        bypass_faulted: bool = False,
        force_arm: bool = False,
        instant: bool = False,
    ) -> AreaControlReply:
        """Send one `!C` command for one or more areas.

        The helper keeps the protocol naming close to the wire format:

        - `areas` is the area list you want to arm
        - `bypass_faulted`, `force_arm`, and `instant` map straight to the
          three option bytes on the command
        """
        transaction = await self._manager.submit(TransactionArmAreas(areas, bypass_faulted=bypass_faulted, force_arm=force_arm, instant=instant))
        parsed = transaction.parsed_response
        if not isinstance(parsed, AreaControlReply):
            raise ValueError("Command completed without a parsed C reply")
        return parsed

    async def disarm_areas(self, areas) -> AreaControlReply:
        """Send one `!O` command for one or more areas."""
        transaction = await self._manager.submit(TransactionDisarmAreas(areas))
        parsed = transaction.parsed_response
        if not isinstance(parsed, AreaControlReply):
            raise ValueError("Command completed without a parsed O reply")
        return parsed

    async def query_zones(self) -> ZoneStatusReply:
        """Return a full zone snapshot from `?WB`.

        The query transaction already handles the area-seeded paging behavior
        that came out of the project captures. This helper simply exposes that
        finished result.
        """
        transaction = await self._manager.submit(TransactionQueryZones())
        parsed = transaction.parsed_response
        if not isinstance(parsed, ZoneStatusReply):
            raise ValueError("Query completed without a parsed WB reply")
        return parsed

    async def query_zone_settings(self, zone: int | str) -> ZoneSettingsReply:
        """Return one direct `?ZLNNN` zone-settings record."""
        transaction = await self._manager.submit(TransactionQueryZoneSettings(zone))
        parsed = transaction.parsed_response
        if not isinstance(parsed, ZoneSettingsReply):
            raise ValueError("Query completed without a parsed ZL reply")
        return parsed

    async def query_area_settings(self, area: int | str) -> AreaSettingsReply:
        """Return one direct `?ZaNN` area-settings record."""
        transaction = await self._manager.submit(TransactionQueryAreaSettings(area))
        parsed = transaction.parsed_response
        if not isinstance(parsed, AreaSettingsReply):
            raise ValueError("Query completed without a parsed Za reply")
        return parsed

    async def query_outputs(
        self,
        start_selector: int | str = "001",
        *,
        namespace: str | None = None,
        named_only: bool = True,
        max_pages: int = 200,
    ) -> OutputStatusReply:
        """Return output status records from `?WQ`.

        By default this follows the safer beginner workflow used elsewhere in
        the repo:

        - start in the numeric output namespace
        - keep only named outputs
        - let callers opt in to `D`, `F`, or `G` explicitly
        """
        transaction = await self._manager.submit(TransactionQueryOutputs(start_selector, namespace=namespace, named_only=named_only, max_pages=max_pages))
        parsed = transaction.parsed_response
        if not isinstance(parsed, OutputStatusReply):
            raise ValueError("Query completed without a parsed WQ reply")
        return parsed

    async def set_output(
        self,
        selector: int | str,
        mode: str | OutputControlMode,
    ) -> OutputControlReply:
        """Send `!Q` for one output selector and return the parsed reply.

        Poll outputs first with `query_outputs()` and keep writes limited to
        selectors known to exist on the current panel.
        """
        transaction = await self._manager.submit(TransactionSetOutput(selector, mode))
        parsed = transaction.parsed_response
        if not isinstance(parsed, OutputControlReply):
            raise ValueError("Command completed without a parsed Q reply")
        return parsed

    async def turn_output_on(self, selector: int | str) -> OutputControlReply:
        """Set one output selector steady/on with `!Q...S`."""
        return await self.set_output(selector, "S")

    async def turn_output_off(self, selector: int | str) -> OutputControlReply:
        """Set one output selector off with `!Q...O`."""
        return await self.set_output(selector, "O")

    async def pulse_output(self, selector: int | str) -> OutputControlReply:
        """Pulse one output selector with `!Q...P`."""
        return await self.set_output(selector, "P")

    async def momentary_output(self, selector: int | str) -> OutputControlReply:
        """Momentarily activate one output selector with `!Q...M`."""
        return await self.set_output(selector, "M")

    async def query_lockout_code(self) -> LockoutCodeReply:
        """Return the current `?ZZ` lockout-code value."""
        transaction = await self._manager.submit(TransactionQueryLockoutCode())
        parsed = transaction.parsed_response
        if not isinstance(parsed, LockoutCodeReply):
            raise ValueError("Query completed without a parsed ZZ reply")
        return parsed

    async def query_users(self) -> UserReply:
        """Return the full visible user table from `?P=`."""
        transaction = await self._manager.submit(TransactionQueryUsers())
        parsed = transaction.parsed_response
        if not isinstance(parsed, UserReply):
            raise ValueError("Query completed without a parsed P= reply")
        return parsed

    async def query_profiles(self) -> ProfileReply:
        """Return the full visible profile table from `?U`."""
        transaction = await self._manager.submit(TransactionQueryProfiles())
        parsed = transaction.parsed_response
        if not isinstance(parsed, ProfileReply):
            raise ValueError("Query completed without a parsed U reply")
        return parsed

    async def sensor_reset(self) -> SensorResetReply:
        """Send `!E001` and return the parsed reply."""
        transaction = await self._manager.submit(TransactionSensorReset())
        parsed = transaction.parsed_response
        if not isinstance(parsed, SensorResetReply):
            raise ValueError("Command completed without a parsed E reply")
        return parsed

    async def bypass_zone(self, zone: int | str) -> ZoneControlReply:
        """Send `!X` for one zone and return the parsed reply."""
        transaction = await self._manager.submit(TransactionBypassZone(zone))
        parsed = transaction.parsed_response
        if not isinstance(parsed, ZoneControlReply):
            raise ValueError("Command completed without a parsed X reply")
        return parsed

    async def unbypass_zone(self, zone: int | str) -> ZoneControlReply:
        """Send `!Y` for one zone and return the parsed reply."""
        transaction = await self._manager.submit(TransactionUnbypassZone(zone))
        parsed = transaction.parsed_response
        if not isinstance(parsed, ZoneControlReply):
            raise ValueError("Command completed without a parsed Y reply")
        return parsed
