"""Public async panel surface backed by the wrapper layer.

This module keeps the historic import path `pydmp.panel.DMPPanel` alive while
internally delegating to the wrapper implementation that sits on the new core.

It also preserves a couple of old module-level seams that tests and older
applications still reach for directly:

- `_ACTIVE_CONNECTIONS`
- `parse_s3_message`
"""

from __future__ import annotations

from typing import Any

from .const.events import DMPEventType
from .status_parser import parse_s3_message
from .wrapper import panel as _wrapper_panel
from .wrapper._compat import status_message_definition

# Keep the old module-level active-connection set name alive. This is the same
# object used by the wrapper panel implementation.
_ACTIVE_CONNECTIONS = _wrapper_panel._ACTIVE_CONNECTIONS


class DMPPanel(_wrapper_panel.DMPPanel):
    """Compatibility panel exposed on the historic `pydmp.panel` path."""

    def attach_status_server(self, server: Any) -> None:
        """Attach one status-server style callback source.

        This override exists so tests that patch `pydmp.panel.parse_s3_message`
        keep working. The wrapper implementation uses its own module import,
        while this public shim should respect the public module path.
        """
        if server in self._status_callbacks:
            return

        async def _callback(message: Any) -> None:
            parsed = None
            try:
                parsed = parse_s3_message(message)
            except Exception:
                parsed = None

            is_user_code_event = False
            if parsed is not None and getattr(parsed, "category", None) is DMPEventType.USER_CODES:
                is_user_code_event = True
            elif status_message_definition(message) == "Zu":
                is_user_code_event = True

            if not is_user_code_event:
                return

            try:
                await self._refresh_user_cache()
            except Exception:
                _wrapper_panel._LOGGER.debug("User cache refresh failed for pushed event", exc_info=True)

        server.register_callback(_callback)
        self._status_callbacks[server] = _callback


__all__ = ["DMPPanel", "_ACTIVE_CONNECTIONS", "parse_s3_message"]
