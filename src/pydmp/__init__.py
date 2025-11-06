"""PyDMP - Python library for controlling DMP alarm systems.

Platform-agnostic library for interfacing with DMP (Digital Monitoring Products)
alarm panels via TCP/IP.

Example (Async):
    >>> import asyncio
    >>> from pydmp import DMPPanel
    >>>
    >>> async def main():
    ...     panel = DMPPanel()
    ...     await panel.connect("192.168.1.100", "00001", "YOUR_KEY")
    ...     areas = await panel.get_areas()
    ...     await areas[0].arm_away("1234")
    ...     await panel.disconnect()
    >>>
    >>> asyncio.run(main())

Example (Sync):
    >>> from pydmp import DMPPanelSync
    >>>
    >>> panel = DMPPanelSync()
    >>> panel.connect("192.168.1.100", "00001", "YOUR_KEY")
    >>> areas = panel.get_areas()
    >>> areas[0].arm_away_sync("1234")
    >>> panel.disconnect()
"""

from . import const, exceptions
from .area import Area, AreaSync
from .connection import DMPConnection
from .connection_sync import DMPConnectionSync
from .crypto import DMPCrypto
from .output import Output, OutputSync
from .panel import DMPPanel
from .panel_sync import DMPPanelSync
from .protocol import DMPProtocol
from .status_server import DMPStatusServer, S3Message
from .status_parser import ParsedEvent, parse_s3_message
from .zone import Zone, ZoneSync

__version__ = "0.1.0"

__all__ = [
    # High-level API (recommended)
    "DMPPanel",
    "DMPPanelSync",
    # Entity classes
    "Area",
    "AreaSync",
    "Zone",
    "ZoneSync",
    "Output",
    "OutputSync",
    # Low-level API (advanced use)
    "DMPConnection",
    "DMPConnectionSync",
    "DMPProtocol",
    "DMPStatusServer",
    "S3Message",
    "ParsedEvent",
    "parse_s3_message",
    "DMPCrypto",
    # Submodules
    "const",
    "exceptions",
    # Version
    "__version__",
]
