"""Synchronous compatibility wrapper for the new-core-backed panel facade."""

from __future__ import annotations

import asyncio
from typing import Any

from ..const.protocol import DEFAULT_PORT
from .area import Area, AreaSync
from .output import Output, OutputSync
from .panel import DMPPanel
from .zone import Zone, ZoneSync


class DMPPanelSync:
    """Sync wrapper that mirrors the old `pydmp.DMPPanelSync` shape."""

    def __init__(self, port: int = DEFAULT_PORT, timeout: float = 10.0):
        self._panel = DMPPanel(port, timeout)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._area_sync_cache: dict[int, AreaSync] = {}
        self._zone_sync_cache: dict[int, ZoneSync] = {}
        self._output_sync_cache: dict[int, OutputSync] = {}

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Return a loop for sync wrapper calls.

        This keeps the old simple `run_until_complete` style rather than
        introducing a more advanced thread-based bridge right away.
        """
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run(self, coro: Any) -> Any:
        return self._get_loop().run_until_complete(coro)

    @property
    def is_connected(self) -> bool:
        return self._panel.is_connected

    def connect(self, host: str, account: str, remote_key: str) -> None:
        self._run(self._panel.connect(host, account, remote_key))

    def disconnect(self) -> None:
        self._run(self._panel.disconnect())

    def update_status(self) -> None:
        self._run(self._panel.update_status())

    def get_areas(self) -> list[AreaSync]:
        return [self._wrap_area(area) for area in self._run(self._panel.get_areas())]

    def get_area(self, number: int) -> AreaSync:
        return self._wrap_area(self._run(self._panel.get_area(number)))

    def get_zones(self) -> list[ZoneSync]:
        return [self._wrap_zone(zone) for zone in self._run(self._panel.get_zones())]

    def get_zone(self, number: int) -> ZoneSync:
        return self._wrap_zone(self._run(self._panel.get_zone(number)))

    def get_outputs(self) -> list[OutputSync]:
        return [self._wrap_output(output) for output in self._run(self._panel.get_outputs())]

    def get_output(self, number: int) -> OutputSync:
        return self._wrap_output(self._run(self._panel.get_output(number)))

    def update_output_status(self) -> None:
        self._run(self._panel.update_output_status())

    def sensor_reset(self) -> None:
        self._run(self._panel.sensor_reset())

    def get_user_codes(self) -> list[Any]:
        return self._run(self._panel.get_user_codes())

    def get_user_profiles(self) -> list[Any]:
        return self._run(self._panel.get_user_profiles())

    def check_code(self, code: str, *, include_pin: bool = True, refresh_if_missing: bool = True):
        return self._run(self._panel.check_code(code, include_pin=include_pin, refresh_if_missing=refresh_if_missing))

    def start_keepalive(self, interval: float = 10.0) -> None:
        self._run(self._panel.start_keepalive(interval))

    def stop_keepalive(self) -> None:
        self._run(self._panel.stop_keepalive())

    def arm_areas(
        self,
        area_numbers: list[int] | tuple[int, ...],
        bypass_faulted: bool = False,
        force_arm: bool = False,
        instant: bool | None = None,
    ) -> None:
        self._run(self._panel.arm_areas(area_numbers, bypass_faulted=bypass_faulted, force_arm=force_arm, instant=instant))

    def disarm_areas(self, area_numbers: list[int] | tuple[int, ...]) -> None:
        self._run(self._panel.disarm_areas(area_numbers))

    def _wrap_area(self, area: Area) -> AreaSync:
        if area.number not in self._area_sync_cache:
            self._area_sync_cache[area.number] = AreaSync(area, self)
        return self._area_sync_cache[area.number]

    def _wrap_zone(self, zone: Zone) -> ZoneSync:
        if zone.number not in self._zone_sync_cache:
            self._zone_sync_cache[zone.number] = ZoneSync(zone, self)
        return self._zone_sync_cache[zone.number]

    def _wrap_output(self, output: Output) -> OutputSync:
        if output.number not in self._output_sync_cache:
            self._output_sync_cache[output.number] = OutputSync(output, self)
        return self._output_sync_cache[output.number]

    def __enter__(self) -> "DMPPanelSync":
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()

    def __repr__(self) -> str:
        return f"<WrapperDMPPanelSync {self._panel}>"
