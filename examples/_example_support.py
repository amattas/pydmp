"""Shared helpers for the new-core examples.

This file keeps the example scripts short and consistent.

The examples are meant to be friendly to someone opening the repo for the first
time, so this helper takes care of a few practical jobs:

- add `pydmp/src` to `sys.path` so examples run from a checkout
- reuse one connection/session CLI surface across the scripts
- give us a few small formatting helpers for raw replies and listener logs
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import sys
from typing import Any

EXAMPLES_DIR = Path(__file__).resolve().parent
PYDMP_DIR = EXAMPLES_DIR.parent
PYDMP_SRC_DIR = PYDMP_DIR / "src"

# These examples live outside the importable package tree, so we add `src`
# once here instead of repeating that setup in every individual script.
if str(PYDMP_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(PYDMP_SRC_DIR))

from pydmp.core import (  # noqa: E402
    CommandSessionManager,
    CorePanelClient,
    PanelEndpoint,
    SessionMode,
    build_session_profile,
)

EXAMPLE_SESSION_MODES = (SessionMode.BLANK_V2, SessionMode.SECURE_S)


def add_panel_connection_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the common panel host/account/port arguments used by read examples."""
    parser.add_argument("--host", required=True, help="Panel IP address or hostname.")
    parser.add_argument("--account", required=True, help="Panel account number, usually 1-5 digits.")
    parser.add_argument("--port", type=int, default=8011, help="Panel TCP port. The local Integrator default is 8011.")


def add_session_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the session options used by these Integrator-focused examples.

    The examples intentionally keep the supported session surface narrow:

    - `blank_v2` for the common unencrypted Integrator lane
    - `secure_s` for passphrase-enabled Integrator sessions

    Keyed V2, V30, and V31 are left out on purpose so the examples stay
    focused on the normal Integrator setup path.
    """
    parser.add_argument("--session-mode", default=SessionMode.BLANK_V2.value, choices=[mode.value for mode in EXAMPLE_SESSION_MODES], help="Integrator command session to use. These examples support only blank_v2 and secure_s.")
    parser.add_argument("--passphrase", help="Passphrase for secure !!S Integrator sessions. Leave this unset for blank V2.")


def add_common_command_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the standard command-lane arguments used by most examples."""
    add_panel_connection_arguments(parser)
    add_session_arguments(parser)
    parser.add_argument("--show-raw", action="store_true", help="Print raw request and reply bytes after the parsed output.")


def build_panel_endpoint_from_args(args: argparse.Namespace) -> PanelEndpoint:
    """Create one normalized panel endpoint from parsed CLI arguments."""
    return PanelEndpoint(
        host=args.host,
        account=args.account,
        port=args.port,
        passphrase=getattr(args, "passphrase", None),
    )


def build_session_profile_from_args(args: argparse.Namespace):
    """Build the requested session profile for the example command lane."""
    mode = SessionMode(args.session_mode)

    if mode is SessionMode.BLANK_V2:
        return build_session_profile(mode)
    if mode is SessionMode.SECURE_S:
        return build_session_profile(mode, passphrase=getattr(args, "passphrase", ""))
    raise ValueError(f"Unsupported session mode: {mode}")


def build_client_from_args(args: argparse.Namespace) -> CorePanelClient:
    """Create the beginner-friendly client used by the simpler examples."""
    endpoint = build_panel_endpoint_from_args(args)
    session_profile = build_session_profile_from_args(args)
    return CorePanelClient(endpoint, session_profile=session_profile)


def build_manager_from_args(args: argparse.Namespace) -> CommandSessionManager:
    """Create the lower-level manager used by direct transaction examples."""
    endpoint = build_panel_endpoint_from_args(args)
    session_profile = build_session_profile_from_args(args)
    return CommandSessionManager(endpoint=endpoint, session_profile=session_profile)


def print_section_heading(title: str) -> None:
    """Print one simple section heading so CLI output is easy to scan."""
    print()
    print(title)
    print("-" * len(title))


def format_bytes_for_cli(data: bytes | None) -> str:
    """Render wire bytes in a readable escaped form for CLI output."""
    if data is None:
        return "<none>"
    return data.decode("ascii", errors="backslashreplace")


def print_transaction_wire_data(wire_requests: list[bytes], wire_responses: list[bytes]) -> None:
    """Print all raw request/reply exchanges recorded on one transaction."""
    print_section_heading("Raw Exchanges")
    for index, request in enumerate(wire_requests, start=1):
        print(f"exchange {index} request: {format_bytes_for_cli(request)}")
        reply = wire_responses[index - 1] if index - 1 < len(wire_responses) else None
        print(f"exchange {index} reply:   {format_bytes_for_cli(reply)}")


def normalize_name_for_display(name: str) -> str:
    """Give blank names a visible placeholder in tables."""
    return name if name else "<blank>"


def make_timestamp_label() -> str:
    """Return a filesystem-friendly local timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def default_listener_log_path(script_stem: str) -> Path:
    """Build the default text log path for the listener example."""
    logs_dir = EXAMPLES_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / f"{script_stem}_{make_timestamp_label()}.txt"


def to_jsonable(value: Any) -> Any:
    """Turn common Python objects into JSON-friendly values for logs.

    This is intentionally small and permissive. The goal is to preserve the
    useful structure of parsed events without forcing the listener example to
    know every event type ahead of time.
    """
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return format_bytes_for_cli(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def pretty_json(value: Any) -> str:
    """Return a stable, indented JSON string for CLI and log output."""
    return json.dumps(to_jsonable(value), indent=2, sort_keys=True)


def run_async_entrypoint(async_main) -> int:
    """Run one async example entrypoint without a traceback on Ctrl+C."""
    try:
        return int(asyncio.run(async_main()) or 0)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
