"""Compatibility output objects backed by the new core."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const.commands import DMPCommand
from ..const.events import DMPRealTimeStatusEvent
from ..exceptions import DMPInvalidParameterError, DMPOutputError
from ._compat import map_output_state

if TYPE_CHECKING:
    from .panel import DMPPanel
    from .panel_sync import DMPPanelSync


class Output:
    """Drop-in style output object for wrapper users."""

    def __init__(self, panel: "DMPPanel", number: int, name: str = "", state: str = "unknown") -> None:
        if not 1 <= number <= 999:
            raise DMPInvalidParameterError("Output number must be between 1 and 999")

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
    def is_on(self) -> bool:
        return self._state == DMPRealTimeStatusEvent.OUTPUT_ON.value

    @property
    def is_off(self) -> bool:
        return self._state == DMPRealTimeStatusEvent.OUTPUT_OFF.value

    @property
    def formatted_number(self) -> str:
        return f"{self.number:03d}"

    async def set_mode(self, mode: str) -> None:
        """Set one output mode through the old command seam."""
        try:
            response = await self.panel._send_command(
                DMPCommand.OUTPUT.value,
                output=self.formatted_number,
                mode=mode,
            )
            if response == "NAK":
                raise DMPOutputError(f"Panel rejected mode {mode} for output {self.number}")

            if mode == "O":
                self._state = DMPRealTimeStatusEvent.OUTPUT_OFF.value
            elif mode == "P":
                self._state = DMPRealTimeStatusEvent.OUTPUT_PULSE.value
            elif mode == "S":
                self._state = DMPRealTimeStatusEvent.OUTPUT_ON.value
            elif mode == "M":
                self._state = DMPRealTimeStatusEvent.OUTPUT_ON.value
            else:
                self._state = map_output_state(mode)
        except Exception as error:
            raise DMPOutputError(f"Failed to set output {self.number} mode: {error}") from error

    async def turn_on(self) -> None:
        await self.set_mode("S")

    async def turn_off(self) -> None:
        await self.set_mode("O")

    async def pulse(self) -> None:
        await self.set_mode("P")

    async def toggle(self) -> None:
        if self.is_on:
            await self.turn_off()
        else:
            await self.turn_on()

    def to_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "name": self.name,
            "state": self.state,
            "is_on": self.is_on,
            "is_off": self.is_off,
        }

    def __repr__(self) -> str:
        return f"<Output {self.number}: {self.name} ({self._state})>"


class OutputSync:
    """Synchronous convenience wrapper for `wrapper.Output`."""

    def __init__(self, output: Output, panel_sync: "DMPPanelSync") -> None:
        self._output = output
        self._panel_sync = panel_sync

    @property
    def number(self) -> int:
        return self._output.number

    @property
    def name(self) -> str:
        return self._output.name

    @property
    def state(self) -> str:
        return self._output.state

    @property
    def is_on(self) -> bool:
        return self._output.is_on

    @property
    def is_off(self) -> bool:
        return self._output.is_off

    def turn_on_sync(self) -> None:
        self._panel_sync._run(self._output.turn_on())

    def turn_off_sync(self) -> None:
        self._panel_sync._run(self._output.turn_off())

    def pulse_sync(self) -> None:
        self._panel_sync._run(self._output.pulse())

    def toggle_sync(self) -> None:
        self._panel_sync._run(self._output.toggle())

    def __repr__(self) -> str:
        return f"<OutputSync {self._output.number}: {self._output.name} ({self._output.state})>"
