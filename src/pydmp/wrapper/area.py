"""Compatibility area objects backed by the new core."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const.commands import DMPCommand
from ..const.responses import (
    AREA_STATUS_ARMED_AWAY,
    AREA_STATUS_ARMED_STAY,
    AREA_STATUS_DISARMED,
)
from ..exceptions import DMPAreaError, DMPInvalidParameterError

if TYPE_CHECKING:
    from .panel import DMPPanel
    from .panel_sync import DMPPanelSync


class Area:
    """Drop-in style area object for wrapper users.

    The public shape stays close to the original `pydmp.Area` class, while the
    work is delegated to `pydmp.wrapper.DMPPanel` and the new core beneath it.
    """

    def __init__(self, panel: "DMPPanel", number: int, name: str = "", state: str = "unknown") -> None:
        if not 1 <= number <= 32:
            raise DMPInvalidParameterError("Area number must be between 1 and 32")

        self.panel = panel
        self.number = number
        self.name = name
        self._state = state

    @property
    def state(self) -> str:
        """Return the current compatibility state string."""
        return self._state

    def update_state(self, state: str, name: str | None = None) -> None:
        """Refresh the cached area state from one new-core poll result."""
        self._state = state
        if name is not None:
            self.name = name

    @property
    def is_armed(self) -> bool:
        """Return True when the area is in any armed state."""
        return self._state in (AREA_STATUS_ARMED_AWAY, AREA_STATUS_ARMED_STAY)

    @property
    def is_disarmed(self) -> bool:
        """Return True when the area is disarmed."""
        return self._state == AREA_STATUS_DISARMED

    async def arm(
        self,
        bypass_faulted: bool = False,
        force_arm: bool = False,
        instant: bool | None = None,
    ) -> None:
        """Arm this area through the old command seam.

        This deliberately uses `_send_command()` instead of going through the
        panel helper method so fake panels from older tests still work.
        """
        try:
            bypass = "Y" if bypass_faulted else "N"
            force = "Y" if force_arm else "N"
            instant_flag = "Y" if instant is True else ("N" if instant is False else "")
            response = await self.panel._send_command(
                DMPCommand.ARM.value,
                area=f"{self.number:02d}",
                bypass=bypass,
                force=force,
                instant=instant_flag,
            )
            if response == "NAK":
                raise DMPAreaError(f"Panel rejected arm command for area {self.number}")
            self._state = "arming"
        except Exception as error:
            raise DMPAreaError(f"Failed to arm area {self.number}: {error}") from error

    async def disarm(self) -> None:
        """Disarm this area through the old command seam."""
        try:
            response = await self.panel._send_command(DMPCommand.DISARM.value, area=f"{self.number:02d}")
            if response == "NAK":
                raise DMPAreaError(f"Panel rejected disarm command for area {self.number}")
            self._state = "disarming"
        except Exception as error:
            raise DMPAreaError(f"Failed to disarm area {self.number}: {error}") from error

    async def get_state(self) -> str:
        """Refresh panel status and return the current area state."""
        await self.panel.update_status()
        return self._state

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly view of this area."""
        return {
            "number": self.number,
            "name": self.name,
            "state": self.state,
            "is_armed": self.is_armed,
            "is_disarmed": self.is_disarmed,
        }

    def __repr__(self) -> str:
        return f"<Area {self.number}: {self.name} ({self._state})>"


class AreaSync:
    """Synchronous convenience wrapper for `wrapper.Area`."""

    def __init__(self, area: Area, panel_sync: "DMPPanelSync") -> None:
        self._area = area
        self._panel_sync = panel_sync

    @property
    def number(self) -> int:
        return self._area.number

    @property
    def name(self) -> str:
        return self._area.name

    @property
    def state(self) -> str:
        return self._area.state

    @property
    def is_armed(self) -> bool:
        return self._area.is_armed

    @property
    def is_disarmed(self) -> bool:
        return self._area.is_disarmed

    def arm_sync(self, bypass_faulted: bool = False, force_arm: bool = False, instant: bool | None = None) -> None:
        """Run `Area.arm()` on the sync wrapper loop."""
        self._panel_sync._run(self._area.arm(bypass_faulted=bypass_faulted, force_arm=force_arm, instant=instant))

    def disarm_sync(self) -> None:
        """Run `Area.disarm()` on the sync wrapper loop."""
        self._panel_sync._run(self._area.disarm())

    def get_state_sync(self) -> str:
        """Run `Area.get_state()` on the sync wrapper loop."""
        return self._panel_sync._run(self._area.get_state())

    def __repr__(self) -> str:
        return f"<AreaSync {self._area.number}: {self._area.name} ({self._area.state})>"
