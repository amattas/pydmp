"""Area abstraction."""

import logging
from typing import TYPE_CHECKING

from .const.commands import DMPCommand
from .exceptions import DMPAreaError, DMPInvalidParameterError
from .const.responses import (
    AREA_STATUS_ARMED_AWAY,
    AREA_STATUS_ARMED_STAY,
    AREA_STATUS_DISARMED,
)

if TYPE_CHECKING:
    from .panel import DMPPanel
    from .panel_sync import DMPPanelSync

_LOGGER = logging.getLogger(__name__)


class Area:
    """Represents a DMP area."""

    def __init__(
        self,
        panel: "DMPPanel",
        number: int,
        name: str = "",
        state: str = "unknown",
    ):
        """Initialize area.

        Args:
            panel: Parent panel instance
            number: Area number (1-8)
            name: Area name
            state: Current area state
        """
        if not 1 <= number <= 8:
            raise DMPInvalidParameterError("Area number must be between 1 and 8")

        self.panel = panel
        self.number = number
        self.name = name
        self._state = state

        _LOGGER.debug(f"Area {number} initialized: {name}")

    @property
    def state(self) -> str:
        """Get current state."""
        return self._state

    def update_state(self, state: str, name: str | None = None) -> None:
        """Update area state from status response.

        Args:
            state: New state
            name: Updated name (optional)
        """
        old_state = self._state
        self._state = state
        if name:
            self.name = name

        if old_state != state:
            _LOGGER.info(f"Area {self.number} state changed: {old_state} → {state}")

    @property
    def is_armed(self) -> bool:
        """Check if area is armed (any armed state)."""
        return self._state in (AREA_STATUS_ARMED_AWAY, AREA_STATUS_ARMED_STAY)

    @property
    def is_disarmed(self) -> bool:
        """Check if area is disarmed."""
        return self._state == AREA_STATUS_DISARMED

    async def arm_away(
        self,
        bypass_faulted: bool = False,
        force_arm: bool = False,
        instant: bool | None = None,
    ) -> None:
        """Arm area in away mode.

        Args:
            bypass_faulted: Bypass faulted zones (default: False)
            force_arm: Force arm bad zones (default: False)
            instant: Remove entry/exit delays (Y/N). If None, omit third flag.

        Raises:
            DMPAreaError: If arm fails
        """
        try:
            _LOGGER.info(
                f"Arming area {self.number} (away, bypass={bypass_faulted}, force={force_arm})"
            )
            bypass = "Y" if bypass_faulted else "N"
            force = "Y" if force_arm else "N"
            instant_flag = "Y" if instant is True else ("N" if instant is False else "")

            response = await self.panel._connection.send_command(
                DMPCommand.ARM.value,
                area=f"{self.number:02d}",
                bypass=bypass,
                force=force,
                instant=instant_flag,
            )

            if response == "NAK":
                raise DMPAreaError(f"Panel rejected arm command for area {self.number}")

            self._state = "arming"
            _LOGGER.info(f"Area {self.number} arm command sent successfully")

        except Exception as e:
            raise DMPAreaError(f"Failed to arm area {self.number}: {e}") from e

    async def arm_stay(
        self,
        bypass_faulted: bool = False,
        force_arm: bool = False,
        instant: bool | None = None,
    ) -> None:
        """Arm area in stay mode.

        Note: DMP protocol doesn't distinguish between away/stay at the protocol level.
        This is provided for API compatibility but uses the same command as arm_away.

        Args:
            bypass_faulted: Bypass faulted zones (default: False)
            force_arm: Force arm bad zones (default: False)

        Raises:
            DMPAreaError: If arm fails
        """
        # DMP uses same command for all arm types
        await self.arm_away(bypass_faulted=bypass_faulted, force_arm=force_arm, instant=instant)

    async def disarm(self) -> None:
        """Disarm area.

        Note: User code validation is typically done at the application level,
        not sent to the panel in the protocol.

        Raises:
            DMPAreaError: If disarm fails
        """
        try:
            _LOGGER.info(f"Disarming area {self.number}")

            response = await self.panel._connection.send_command(
                DMPCommand.DISARM.value,
                area=f"{self.number:02d}",
            )

            if response == "NAK":
                raise DMPAreaError(f"Panel rejected disarm command for area {self.number}")

            self._state = "disarming"
            _LOGGER.info(f"Area {self.number} disarm command sent successfully")

        except Exception as e:
            raise DMPAreaError(f"Failed to disarm area {self.number}: {e}") from e

    async def get_state(self) -> str:
        """Get current state from panel.

        Returns:
            Current area state
        """
        await self.panel.update_status()
        return self._state

    def __repr__(self) -> str:
        """String representation."""
        return f"<Area {self.number}: {self.name} ({self._state})>"


class AreaSync:
    """Synchronous wrapper for Area."""

    def __init__(self, area: Area, panel_sync: "DMPPanelSync"):
        """Initialize sync area.

        Args:
            area: Async Area instance
            panel_sync: Sync panel instance
        """
        self._area = area
        self._panel_sync = panel_sync

    @property
    def number(self) -> int:
        """Get area number."""
        return self._area.number

    @property
    def name(self) -> str:
        """Get area name."""
        return self._area.name

    @property
    def state(self) -> str:
        """Get current state."""
        return self._area.state

    @property
    def is_armed(self) -> bool:
        """Check if area is armed."""
        return self._area.is_armed

    @property
    def is_disarmed(self) -> bool:
        """Check if area is disarmed."""
        return self._area.is_disarmed

    def arm_away_sync(self, bypass_faulted: bool = False, force_arm: bool = False) -> None:
        """Arm area in away mode (sync)."""
        self._panel_sync._run(self._area.arm_away(bypass_faulted, force_arm))

    def arm_stay_sync(self, bypass_faulted: bool = False, force_arm: bool = False) -> None:
        """Arm area in stay mode (sync)."""
        self._panel_sync._run(self._area.arm_stay(bypass_faulted, force_arm))

    def disarm_sync(self) -> None:
        """Disarm area (sync)."""
        self._panel_sync._run(self._area.disarm())

    def get_state_sync(self) -> str:
        """Get current state from panel (sync)."""
        return self._panel_sync._run(self._area.get_state())

    def __repr__(self) -> str:
        """String representation."""
        return f"<AreaSync {self._area.number}: {self._area.name} ({self._area.state})>"
