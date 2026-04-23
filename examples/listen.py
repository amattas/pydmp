"""Run the new-core push listener and save a text log.

This example prints each inbound push to the terminal and writes the same
details to a timestamped text file. That makes it useful for day-to-day live
testing and for saving traffic that we may want to study later.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from _example_support import default_listener_log_path, format_bytes_for_cli, pretty_json, run_async_entrypoint
from pydmp.core import DMPPushListener, ListenerProfilePush, PushMessage


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Run the new-core DMP push listener and save a text log.")
    parser.add_argument("--listen-host", required=True, help="Local host or interface to bind, such as 0.0.0.0 or one specific local address.")
    parser.add_argument("--listen-port", type=int, default=8001, help="Local TCP port to listen on. The Integrator listener default is 8001.")
    parser.add_argument("--passphrase", action="append", default=[], help="Secure !!S passphrase for encrypted Integrator push traffic. Repeat this option to accept more than one.")
    parser.add_argument("--log-path", help="Optional explicit text log path. A timestamped path under examples/logs is used by default.")
    return parser


def render_message_block(message: PushMessage) -> str:
    """Render one parsed push message as a readable multi-line text block."""
    lines: list[str] = []
    lines.append(f"time: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"transport_mode: {message.transport_mode.value}")
    lines.append(f"account: {message.account or '<none>'}")
    lines.append(f"raw_frame: {format_bytes_for_cli(message.raw_frame)}")
    lines.append(f"clear_frame: {format_bytes_for_cli(message.clear_frame)}")
    lines.append(f"normalized_frame: {format_bytes_for_cli(message.normalized_frame)}")

    if message.event is not None:
        lines.append(f"event_definition: {message.event.definition}")
        lines.append(f"event_raw: {message.event.raw}")
        lines.append(f"event_fields: {pretty_json(message.event.fields)}")
        lines.append(f"event_parser: {message.event.parser_name or '<none>'}")
        lines.append(f"event_parsed: {pretty_json(message.event.parsed)}")
    else:
        lines.append("event_definition: <none>")

    if message.special is not None:
        lines.append(f"special: {pretty_json(message.special)}")

    lines.append(f"ack_frame: {format_bytes_for_cli(message.ack_frame)}")

    if message.wrapper_crc_hex is not None:
        lines.append(f"wrapper_crc_hex: {message.wrapper_crc_hex}")
        lines.append(f"wrapper_crc_calc: {message.wrapper_crc_calc}")
        lines.append(f"wrapper_crc_valid: {message.wrapper_crc_valid}")
        lines.append(f"route_token: {message.route_token}")
        lines.append(f"delivery_field: {message.delivery_field}")

    return "\n".join(lines)


async def async_main() -> int:
    """Run the listener until the process is interrupted."""
    args = build_parser().parse_args()
    log_path = Path(args.log_path) if args.log_path else default_listener_log_path("listen")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    profile = ListenerProfilePush(secure_passphrases=args.passphrase)
    listener = DMPPushListener(listen_host=args.listen_host, listen_port=args.listen_port, profile=profile)

    with log_path.open("a", encoding="utf-8", buffering=1) as log_file:
        def write_block(block: str) -> None:
            print()
            print(block)
            print()
            log_file.write(block + "\n\n")

        async def handle_message(message: PushMessage) -> None:
            write_block(render_message_block(message))

        listener.register_callback(handle_message)
        await listener.start()
        print(f"Listening on {args.listen_host}:{args.listen_port}")
        print(f"Logging to {log_path}")

        try:
            await asyncio.Event().wait()
        finally:
            await listener.stop()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 listen.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
