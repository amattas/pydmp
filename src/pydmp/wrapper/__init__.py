"""Compatibility wrapper package for migrating old `pydmp` code to the new core.

Import from `pydmp.wrapper` when you want the old high-level panel/entity API
shape but the new core underneath.
"""

from .area import Area, AreaSync
from .output import Output, OutputSync
from .panel import DMPPanel
from .panel_sync import DMPPanelSync
from .zone import Zone, ZoneSync

__all__ = [
    "DMPPanel",
    "DMPPanelSync",
    "Area",
    "AreaSync",
    "Zone",
    "ZoneSync",
    "Output",
    "OutputSync",
]
