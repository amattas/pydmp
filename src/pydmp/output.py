"""Output abstraction."""

import logging
from typing import TYPE_CHECKING

from .const.commands import DMPCommand
from .const.events import DMPRealTimeStatusEvent
from .exceptions import DMPInvalidParameterError, DMPOutputError

if TYPE_CHECKING:
    from .panel import DMPPanel
    from .panel_sync import DMPPanelSync

_LOGGER = logging.getLogger(__name__)


class Output:
    """Represents a DMP output."""

    def __init__(
        self,
        panel: "DMPPanel",
        number: int,
        name: str = "",
        state: str = "unknown",
    ):
        """Initialize output.

        Args:
            panel: Parent panel instance
            number: Output number (1-4)
            name: Output name
            state: Current output state
        """
        if not 1 <= number <= 999:
            raise DMPInvalidParameterError("Output number must be between 1 and 999")

        self.panel = panel
        self.number = number
        self.name = name
        self._state = state

        _LOGGER.debug(f"Output {number} initialized: {name}")

    @property
    def state(self) -> str:
        """Get current state."""
        return self._state

    def update_state(self, state: str, name: str | None = None) -> None:
        """Update output state.

        Args:
            state: New state
            name: Updated name (optional)
        """
        old_state = self._state
        self._state = state
        if name:
            self.name = name

        if old_state != state:
            _LOGGER.info(f"Output {self.number} state changed: {old_state} → {state}")

    @property
    def is_on(self) -> bool:
        """Check if output is on."""
        return self._state == DMPRealTimeStatusEvent.OUTPUT_ON.value

    @property
    def is_off(self) -> bool:
        """Check if output is off."""
        return self._state == DMPRealTimeStatusEvent.OUTPUT_OFF.value

    @property
    def formatted_number(self) -> str:
        """Get zero-padded 3-digit output number."""
        return f"{self.number:03d}"

    async def set_mode(self, mode: str) -> None:
        """Set output mode.

        Args:
            mode: Output mode ('O'=Off, 'P'=Pulse, 'S'=Steady, 'M'=Momentary)

        Raises:
            DMPOutputError: If command fails
        """
        try:
            _LOGGER.info(f"Setting output {self.number} to mode {mode}")

            response = await self.panel._connection.send_command(
                DMPCommand.OUTPUT.value,
                output=self.formatted_number,
                mode=mode
            )

            if response == "NAK":
                raise DMPOutputError(f"Panel rejected mode {mode} for output {self.number}")

            # Update state based on mode
            if mode == "O":
                self._state = DMPRealTimeStatusEvent.OUTPUT_OFF.value
            elif mode == "P":
                self._state = DMPRealTimeStatusEvent.OUTPUT_PULSE.value
            elif mode == "S":
                self._state = DMPRealTimeStatusEvent.OUTPUT_ON.value
            elif mode == "M":
                self._state = DMPRealTimeStatusEvent.OUTPUT_ON.value

            _LOGGER.info(f"Output {self.number} set to mode {mode} successfully")

        except Exception as e:
            raise DMPOutputError(f"Failed to set output {self.number} mode: {e}") from e

    async def turn_on(self) -> None:
        """Turn output on (steady mode).

        Raises:
            DMPOutputError: If command fails
        """
        await self.set_mode("S")

    async def turn_off(self) -> None:
        """Turn output off.

        Raises:
            DMPOutputError: If command fails
        """
        await self.set_mode("O")

    async def pulse(self) -> None:
        """Pulse output (momentary activation).

        Raises:
            DMPOutputError: If command fails
        """
        await self.set_mode("P")

    async def toggle(self) -> None:
        """Toggle output state.

        Raises:
            DMPOutputError: If command fails
        """
        # Toggle between steady and off
        if self._state == DMPRealTimeStatusEvent.OUTPUT_ON.value:
            await self.turn_off()
        else:
            await self.turn_on()

    def __repr__(self) -> str:
        """String representation."""
        return f"<Output {self.number}: {self.name} ({self._state})>"

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation of the output."""
        return {
            "number": self.number,
            "name": self.name,
            "state": self.state,
            "is_on": self.is_on,
            "is_off": self.is_off,
        }


class OutputSync:
    """Synchronous wrapper for Output."""

    def __init__(self, output: Output, panel_sync: "DMPPanelSync"):
        """Initialize sync output.

        Args:
            output: Async Output instance
            panel_sync: Sync panel instance
        """
        self._output = output
        self._panel_sync = panel_sync

    @property
    def number(self) -> int:
        """Get output number."""
        return self._output.number

    @property
    def name(self) -> str:
        """Get output name."""
        return self._output.name

    @property
    def state(self) -> str:
        """Get current state."""
        return self._output.state

    @property
    def is_on(self) -> bool:
        """Check if output is on."""
        return self._output.is_on

    @property
    def is_off(self) -> bool:
        """Check if output is off."""
        return self._output.is_off

    def turn_on_sync(self) -> None:
        """Turn output on (sync)."""
        self._panel_sync._run(self._output.turn_on())

    def turn_off_sync(self) -> None:
        """Turn output off (sync)."""
        self._panel_sync._run(self._output.turn_off())

    def pulse_sync(self) -> None:
        """Pulse output (sync)."""
        self._panel_sync._run(self._output.pulse())

    def toggle_sync(self) -> None:
        """Toggle output (sync)."""
        self._panel_sync._run(self._output.toggle())

    def __repr__(self) -> str:
        """String representation."""
        return f"<OutputSync {self._output.number}: {self._output.name} ({self._output.state})>"
