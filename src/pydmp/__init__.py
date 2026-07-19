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
    ...     await areas[0].arm()
    ...     await panel.disconnect()
    >>>
    >>> asyncio.run(main())

Example (Sync):
    >>> from pydmp import DMPPanelSync
    >>>
    >>> panel = DMPPanelSync()
    >>> panel.connect("192.168.1.100", "00001", "YOUR_KEY")
    >>> areas = panel.get_areas()
    >>> areas[0].arm_sync()
    >>> panel.disconnect()
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

from . import const, exceptions
from .area import Area, AreaSync
from .crypto import DMPCrypto
from .output import Output, OutputSync
from .panel import DMPPanel
from .panel_sync import DMPPanelSync
from .protocol import DMPProtocol
from .status_parser import ParsedEvent, parse_s3_message
from .status_server import DMPStatusServer, S3Message
from .transport import DMPTransport
from .transport_sync import DMPTransportSync
from .zone import Zone, ZoneSync


def _runtime_version() -> str:
    """pyproject's static version is the single source of truth (the aviato release
    automation writes it); derive from installed metadata, falling back to reading
    pyproject directly for uninstalled source checkouts."""
    try:
        return _dist_version("pydmp")
    except PackageNotFoundError:
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
        if not isinstance(version, str):
            raise RuntimeError(f"{pyproject} does not define a string project.version")
        return version


__version__ = _runtime_version()

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
    "DMPTransport",
    "DMPTransportSync",
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

# Note: No backward-compatibility aliases are provided.
