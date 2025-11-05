"""High-level synchronous panel controller."""

import asyncio
import logging
from typing import Any

from .area import Area, AreaSync
from .const.commands import DEFAULT_PORT
from .output import Output, OutputSync
from .panel import DMPPanel
from .zone import Zone, ZoneSync

_LOGGER = logging.getLogger(__name__)


class DMPPanelSync:
    """High-level synchronous interface to DMP panel."""

    def __init__(self, port: int = DEFAULT_PORT, timeout: float = 10.0):
        """Initialize sync panel.

        Args:
            port: TCP port (default: 2011)
            timeout: Connection timeout in seconds
        """
        self._panel = DMPPanel(port, timeout)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._area_sync_cache: dict[int, AreaSync] = {}
        self._zone_sync_cache: dict[int, ZoneSync] = {}
        self._output_sync_cache: dict[int, OutputSync] = {}

        _LOGGER.debug("Sync panel initialized")

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run(self, coro: Any) -> Any:
        """Run coroutine synchronously."""
        loop = self._get_loop()
        return loop.run_until_complete(coro)

    @property
    def is_connected(self) -> bool:
        """Check if connected to panel."""
        return self._panel.is_connected

    def connect(self, host: str, account: str, remote_key: str) -> None:
        """Connect to panel and authenticate.

        Args:
            host: Panel IP address or hostname
            account: 5-digit account number
            remote_key: Remote key for authentication
        """
        self._run(self._panel.connect(host, account, remote_key))

    def disconnect(self) -> None:
        """Disconnect from panel."""
        self._run(self._panel.disconnect())

    def update_status(self) -> None:
        """Update status of all areas and zones from panel."""
        self._run(self._panel.update_status())

    def get_areas(self) -> list[AreaSync]:
        """Get all areas.

        Returns:
            List of AreaSync objects
        """
        areas = self._run(self._panel.get_areas())
        return [self._wrap_area(area) for area in areas]

    def get_area(self, number: int) -> AreaSync:
        """Get specific area by number.

        Args:
            number: Area number (1-8)

        Returns:
            AreaSync object
        """
        area = self._run(self._panel.get_area(number))
        return self._wrap_area(area)

    def get_zones(self) -> list[ZoneSync]:
        """Get all zones.

        Returns:
            List of ZoneSync objects
        """
        zones = self._run(self._panel.get_zones())
        return [self._wrap_zone(zone) for zone in zones]

    def get_zone(self, number: int) -> ZoneSync:
        """Get specific zone by number.

        Args:
            number: Zone number (1-999)

        Returns:
            ZoneSync object
        """
        zone = self._run(self._panel.get_zone(number))
        return self._wrap_zone(zone)

    def get_outputs(self) -> list[OutputSync]:
        """Get all outputs.

        Returns:
            List of OutputSync objects
        """
        outputs = self._run(self._panel.get_outputs())
        return [self._wrap_output(output) for output in outputs]

    def get_output(self, number: int) -> OutputSync:
        """Get specific output by number.

        Args:
            number: Output number (1-4)

        Returns:
            OutputSync object
        """
        output = self._run(self._panel.get_output(number))
        return self._wrap_output(output)

    def trigger_fire_emergency(self) -> None:
        """Trigger fire emergency alarm."""
        self._run(self._panel.trigger_fire_emergency())

    def trigger_police_emergency(self) -> None:
        """Trigger police emergency alarm."""
        self._run(self._panel.trigger_police_emergency())

    def trigger_medical_emergency(self) -> None:
        """Trigger medical emergency alarm."""
        self._run(self._panel.trigger_medical_emergency())

    def _wrap_area(self, area: Area) -> AreaSync:
        """Wrap async Area in AreaSync."""
        if area.number not in self._area_sync_cache:
            self._area_sync_cache[area.number] = AreaSync(area, self)
        return self._area_sync_cache[area.number]

    def _wrap_zone(self, zone: Zone) -> ZoneSync:
        """Wrap async Zone in ZoneSync."""
        if zone.number not in self._zone_sync_cache:
            self._zone_sync_cache[zone.number] = ZoneSync(zone, self)
        return self._zone_sync_cache[zone.number]

    def _wrap_output(self, output: Output) -> OutputSync:
        """Wrap async Output in OutputSync."""
        if output.number not in self._output_sync_cache:
            self._output_sync_cache[output.number] = OutputSync(output, self)
        return self._output_sync_cache[output.number]

    def __enter__(self) -> "DMPPanelSync":
        """Context manager entry."""
        # Panel is created unconnected, user must call connect()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.disconnect()

    def __repr__(self) -> str:
        """String representation."""
        return f"<DMPPanelSync {self._panel}>"
