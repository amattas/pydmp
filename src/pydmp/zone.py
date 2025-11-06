"""Zone abstraction."""

import logging
from typing import TYPE_CHECKING

from .const.commands import DMPCommand
from .const.responses import (
    ZONE_STATUS_BYPASSED,
    ZONE_STATUS_LOW_BATTERY,
    ZONE_STATUS_MISSING,
    ZONE_STATUS_NORMAL,
    ZONE_STATUS_OPEN,
    ZONE_STATUS_SHORT,
)
from .exceptions import DMPInvalidParameterError, DMPZoneError

if TYPE_CHECKING:
    from .panel import DMPPanel
    from .panel_sync import DMPPanelSync

_LOGGER = logging.getLogger(__name__)


class Zone:
    """Represents a DMP zone."""

    def __init__(
        self,
        panel: "DMPPanel",
        number: int,
        name: str = "",
        state: str = "unknown",
    ):
        """Initialize zone.

        Args:
            panel: Parent panel instance
            number: Zone number (1-999)
            name: Zone name
            zone_type: Type of zone
            state: Current zone state
        """
        if not 1 <= number <= 999:
            raise DMPInvalidParameterError("Zone number must be between 1 and 999")

        self.panel = panel
        self.number = number
        self.name = name
        self._state = state

        _LOGGER.debug(f"Zone {number} initialized: {name}")

    @property
    def state(self) -> str:
        """Get current state."""
        return self._state

    def update_state(self, state: str, name: str | None = None) -> None:
        """Update zone state from status response.

        Args:
            state: New state
            name: Updated name (optional)
            zone_type: Updated type (optional)
        """
        old_state = self._state
        self._state = state
        if name:
            self.name = name

        if old_state != state:
            _LOGGER.info(f"Zone {self.number} state changed: {old_state} → {state}")

    @property
    def is_open(self) -> bool:
        """Check if zone is open/tripped."""
        return self._state == ZONE_STATUS_OPEN

    @property
    def is_normal(self) -> bool:
        """Check if zone is normal (closed)."""
        return self._state == ZONE_STATUS_NORMAL

    @property
    def is_bypassed(self) -> bool:
        """Check if zone is bypassed."""
        return self._state == ZONE_STATUS_BYPASSED

    @property
    def has_fault(self) -> bool:
        """Check if zone has a fault."""
        return self._state in (
            ZONE_STATUS_SHORT,
            ZONE_STATUS_LOW_BATTERY,
            ZONE_STATUS_MISSING,
        )

    @property
    def formatted_number(self) -> str:
        """Get zero-padded 3-digit zone number."""
        return f"{self.number:03d}"

    async def bypass(self) -> None:
        """Bypass this zone.

        Raises:
            DMPZoneError: If bypass fails
        """
        try:
            _LOGGER.info("Bypassing zone %s", self.number)

            response = await self.panel._send_command(
                DMPCommand.BYPASS_ZONE.value, zone=self.formatted_number
            )

            if response == "NAK":
                raise DMPZoneError(f"Panel rejected bypass command for zone {self.number}")

            _LOGGER.info("Zone %s bypassed", self.number)

        except Exception as e:
            raise DMPZoneError(f"Failed to bypass zone {self.number}: {e}") from e

    async def restore(self) -> None:
        """Restore (un-bypass) this zone.

        Raises:
            DMPZoneError: If restore fails
        """
        try:
            _LOGGER.info("Restoring zone %s", self.number)

            response = await self.panel._send_command(
                DMPCommand.RESTORE_ZONE.value, zone=self.formatted_number
            )

            if response == "NAK":
                raise DMPZoneError(f"Panel rejected restore command for zone {self.number}")

            _LOGGER.info("Zone %s restored", self.number)

        except Exception as e:
            raise DMPZoneError(f"Failed to restore zone {self.number}: {e}") from e

    async def get_state(self) -> str:
        """Get current state from panel.

        Returns:
            Current zone state
        """
        await self.panel.update_status()
        return self._state

    def __repr__(self) -> str:
        """String representation."""
        return f"<Zone {self.number}: {self.name} ({self._state})>"

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation of the zone."""
        return {
            "number": self.number,
            "name": self.name,
            "state": self.state,
            "is_open": self.is_open,
            "is_normal": self.is_normal,
            "is_bypassed": self.is_bypassed,
            "has_fault": self.has_fault,
        }


class ZoneSync:
    """Synchronous wrapper for Zone."""

    def __init__(self, zone: Zone, panel_sync: "DMPPanelSync"):
        """Initialize sync zone.

        Args:
            zone: Async Zone instance
            panel_sync: Sync panel instance
        """
        self._zone = zone
        self._panel_sync = panel_sync

    @property
    def number(self) -> int:
        """Get zone number."""
        return self._zone.number

    @property
    def name(self) -> str:
        """Get zone name."""
        return self._zone.name

    @property
    @property
    def state(self) -> str:
        """Get current state."""
        return self._zone.state

    @property
    def is_open(self) -> bool:
        """Check if zone is open."""
        return self._zone.is_open

    @property
    def is_normal(self) -> bool:
        """Check if zone is normal."""
        return self._zone.is_normal

    @property
    def is_bypassed(self) -> bool:
        """Check if zone is bypassed."""
        return self._zone.is_bypassed

    @property
    def has_fault(self) -> bool:
        """Check if zone has fault."""
        return self._zone.has_fault

    @property
    def formatted_number(self) -> str:
        """Get formatted number."""
        return self._zone.formatted_number

    def bypass_sync(self) -> None:
        """Bypass zone (sync)."""
        self._panel_sync._run(self._zone.bypass())

    def restore_sync(self) -> None:
        """Restore zone (sync)."""
        self._panel_sync._run(self._zone.restore())

    def get_state_sync(self) -> str:
        """Get current state from panel (sync)."""
        return self._panel_sync._run(self._zone.get_state())

    def __repr__(self) -> str:
        """String representation."""
        return f"<ZoneSync {self._zone.number}: {self._zone.name} ({self._zone.state})>"
