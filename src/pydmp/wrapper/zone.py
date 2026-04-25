"""Compatibility zone objects backed by the new core."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const.commands import DMPCommand
from ..const.responses import (
    ZONE_STATUS_BYPASSED,
    ZONE_STATUS_LOW_BATTERY,
    ZONE_STATUS_MISSING,
    ZONE_STATUS_NORMAL,
    ZONE_STATUS_OPEN,
    ZONE_STATUS_SHORT,
)
from ..exceptions import DMPInvalidParameterError, DMPZoneError

if TYPE_CHECKING:
    from .panel import DMPPanel
    from .panel_sync import DMPPanelSync


class Zone:
    """Drop-in style zone object for wrapper users."""

    def __init__(self, panel: "DMPPanel", number: int, name: str = "", state: str = "unknown") -> None:
        if not 1 <= number <= 999:
            raise DMPInvalidParameterError("Zone number must be between 1 and 999")

        self.panel = panel
        self.number = number
        self.name = name
        self._state = state

    @property
    def state(self) -> str:
        return self._state

    def update_state(self, state: str, name: str | None = None) -> None:
        self._state = state
        if name is not None:
            self.name = name

    @property
    def is_open(self) -> bool:
        return self._state == ZONE_STATUS_OPEN

    @property
    def is_normal(self) -> bool:
        return self._state == ZONE_STATUS_NORMAL

    @property
    def is_bypassed(self) -> bool:
        return self._state == ZONE_STATUS_BYPASSED

    @property
    def has_fault(self) -> bool:
        return self._state in (ZONE_STATUS_SHORT, ZONE_STATUS_LOW_BATTERY, ZONE_STATUS_MISSING)

    @property
    def formatted_number(self) -> str:
        return f"{self.number:03d}"

    async def bypass(self) -> None:
        """Bypass this zone through the old command seam."""
        try:
            response = await self.panel._send_command(
                DMPCommand.BYPASS_ZONE.value,
                zone=self.formatted_number,
            )
            if response == "NAK":
                detail = getattr(getattr(self.panel, "_protocol", None), "last_nak_detail", None)
                if detail:
                    raise DMPZoneError(f"Panel rejected bypass command for zone {self.number} ({detail})")
                raise DMPZoneError(f"Panel rejected bypass command for zone {self.number}")
        except Exception as error:
            raise DMPZoneError(f"Failed to bypass zone {self.number}: {error}") from error

    async def restore(self) -> None:
        """Remove bypass on this zone through the old command seam."""
        try:
            response = await self.panel._send_command(
                DMPCommand.RESTORE_ZONE.value,
                zone=self.formatted_number,
            )
            if response == "NAK":
                detail = getattr(getattr(self.panel, "_protocol", None), "last_nak_detail", None)
                if detail:
                    raise DMPZoneError(f"Panel rejected restore command for zone {self.number} ({detail})")
                raise DMPZoneError(f"Panel rejected restore command for zone {self.number}")
        except Exception as error:
            raise DMPZoneError(f"Failed to restore zone {self.number}: {error}") from error

    async def get_state(self) -> str:
        await self.panel.update_status()
        return self._state

    def to_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "name": self.name,
            "state": self.state,
            "is_open": self.is_open,
            "is_normal": self.is_normal,
            "is_bypassed": self.is_bypassed,
            "has_fault": self.has_fault,
        }

    def __repr__(self) -> str:
        return f"<Zone {self.number}: {self.name} ({self._state})>"


class ZoneSync:
    """Synchronous convenience wrapper for `wrapper.Zone`."""

    def __init__(self, zone: Zone, panel_sync: "DMPPanelSync") -> None:
        self._zone = zone
        self._panel_sync = panel_sync

    @property
    def number(self) -> int:
        return self._zone.number

    @property
    def name(self) -> str:
        return self._zone.name

    @property
    def state(self) -> str:
        return self._zone.state

    @property
    def is_open(self) -> bool:
        return self._zone.is_open

    @property
    def is_normal(self) -> bool:
        return self._zone.is_normal

    @property
    def is_bypassed(self) -> bool:
        return self._zone.is_bypassed

    @property
    def has_fault(self) -> bool:
        return self._zone.has_fault

    @property
    def formatted_number(self) -> str:
        return self._zone.formatted_number

    def bypass_sync(self) -> None:
        self._panel_sync._run(self._zone.bypass())

    def restore_sync(self) -> None:
        self._panel_sync._run(self._zone.restore())

    def get_state_sync(self) -> str:
        return self._panel_sync._run(self._zone.get_state())

    def __repr__(self) -> str:
        return f"<ZoneSync {self._zone.number}: {self._zone.name} ({self._zone.state})>"
