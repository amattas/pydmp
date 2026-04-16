#!/usr/bin/env python3
"""Simple runnable example for the new stateless core."""

from __future__ import annotations

import argparse
import asyncio

from pydmp.core import (
    CommandSessionManager,
    DMPPushListener,
    ListenerProfilePush,
    PanelEndpoint,
    PushMessage,
    SessionMode,
    TransactionQueryAreas,
    TransactionQueryZones,
    build_session_profile,
)


def build_args() -> argparse.Namespace:
    """Parse command-line arguments for the example."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the new stateless pydmp core against a panel or start "
            "the new-core push listener and print inbound events."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("query", "listen"),
        default="query",
        help="Run panel queries or start the push listener. Default: query.",
    )
    parser.add_argument("--host", help="Panel host or IP address.")
    parser.add_argument("--account", help="Panel account number.")
    parser.add_argument("--port", type=int, default=8011, help="Panel TCP port. Default: 8011.")
    parser.add_argument(
        "--listen-host",
        default="0.0.0.0",
        help="Listener bind host. Default: 0.0.0.0.",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=8001,
        help="Listener bind port. Default: 8001.",
    )
    parser.add_argument(
        "--session-type",
        choices=[mode.value for mode in SessionMode],
        default=SessionMode.BLANK_V2.value,
        help="Session profile to use. Default: blank_v2.",
    )
    parser.add_argument(
        "--remote-key",
        default=None,
        help="Remote key for keyed_v2 sessions.",
    )
    parser.add_argument(
        "--v31-material",
        default=None,
        help="Compare material for v31 sessions.",
    )
    parser.add_argument(
        "--panel-serial",
        default=None,
        help="8-hex panel serial for v30 sessions.",
    )
    parser.add_argument(
        "--user-code",
        default=None,
        help="User code for v30 sessions.",
    )
    parser.add_argument(
        "--passphrase",
        default=None,
        help="Passphrase for secure_s sessions.",
    )
    parser.add_argument(
        "--v30-tail4",
        default=None,
        help="Optional 4-byte V30 tail override. Default is profile behavior.",
    )
    parser.add_argument(
        "--area",
        default="01",
        help="Starting area for QueryAreas. Default: 01.",
    )
    parser.add_argument(
        "--skip-areas",
        action="store_true",
        help="Skip TransactionQueryAreas.",
    )
    parser.add_argument(
        "--skip-zones",
        action="store_true",
        help="Skip TransactionQueryZones.",
    )
    return parser.parse_args()


def print_section(title: str) -> None:
    """Print a short section header."""
    print()
    print(title)
    print("-" * len(title))


def print_area_transaction(transaction) -> None:
    """Print one completed QueryAreas transaction."""
    print_section("QueryAreas")
    print("Wire requests:")
    for request in transaction.wire_requests:
        print(" ", request)
    print("Raw last reply:", transaction.response)
    print("All raw replies:")
    for raw_reply in transaction.parsed_response.raw_replies:
        print(" ", raw_reply)
    print("Areas:")
    for area in transaction.parsed_response.areas:
        print(f"  number:        {area.number}")
        print(f"  arming_state:  {area.arming_state}")
        print(f"  status_2:      {area.status_2}")
        print(f"  status_3:      {area.status_3}")
        print(f"  status_4:      {area.status_4}")
        print(f"  name:          {area.name}")
        print()


def print_zone_transaction(transaction) -> None:
    """Print one completed QueryZones transaction."""
    print_section("QueryZones")
    print("Wire requests:")
    for request in transaction.wire_requests:
        print(" ", request)
    print("Raw last reply:", transaction.response)
    print("All raw replies:")
    for raw_reply in transaction.parsed_response.raw_replies:
        print(" ", raw_reply)
    print("Areas discovered:")
    for area in transaction.parsed_response.areas:
        print(f"  number:        {area.number}")
        print(f"  arming_state:  {area.arming_state}")
        print(f"  status_2:      {area.status_2}")
        print(f"  status_3:      {area.status_3}")
        print(f"  status_4:      {area.status_4}")
        print(f"  name:          {area.name}")
        print()
    print("Zones:")
    for zone in transaction.parsed_response.zones:
        print(f"  number:        {zone.number}")
        print(f"  area_number:   {zone.area_number}")
        print(f"  status:        {zone.status}")
        print(f"  name:          {zone.name}")
        print()


def escape_bytes(data: bytes) -> str:
    """Render bytes in a readable CLI-safe form."""
    chunks: list[str] = []
    for byte_value in data:
        if 32 <= byte_value <= 126:
            chunks.append(chr(byte_value))
        elif byte_value == 9:
            chunks.append("\\t")
        elif byte_value == 10:
            chunks.append("\\n")
        elif byte_value == 13:
            chunks.append("\\r")
        else:
            chunks.append(f"\\x{byte_value:02x}")
    return "".join(chunks)


def print_push_message(message: PushMessage) -> None:
    """Print one inbound push message to the CLI."""
    print()
    print(
        "Push"
        f" mode={message.transport_mode.value}"
        f" account={message.account or '(none)'}"
    )
    print(f"  raw:           {escape_bytes(message.raw_frame)}")
    print(f"  raw hex:       {message.raw_frame.hex(' ')}")
    print(f"  clear:         {escape_bytes(message.clear_frame)}")
    print(f"  clear hex:     {message.clear_frame.hex(' ')}")

    if message.ack_frame is not None:
        print(f"  ack:           {escape_bytes(message.ack_frame)}")
        print(f"  ack hex:       {message.ack_frame.hex(' ')}")

    if message.wrapper_crc_hex is not None:
        print(
            "  wrapper:       "
            f"crc={message.wrapper_crc_hex} "
            f"calc={message.wrapper_crc_calc} "
            f"valid={message.wrapper_crc_valid}"
        )
    if message.route_token is not None:
        print(f"  route token:   {message.route_token}")
    if message.delivery_field is not None:
        print(f"  delivery:      {message.delivery_field}")

    if message.special is not None:
        print(f"  special:       {message.special.kind}")
        print(f"  interval_min:  {message.special.interval_minutes}")
        print(f"  detail:        {message.special.detail}")
        print(f"  special raw:   {message.special.raw}")

    if message.event is None:
        print("  parsed event:  none")
        return

    event = message.event
    print(f"  definition:    {event.definition}")
    print(f"  type_code:     {event.type_code}")
    print(f"  area:          {event.area}")
    print(f"  area_name:     {event.area_name}")
    print(f"  zone:          {event.zone}")
    print(f"  zone_name:     {event.zone_name}")
    print(f"  user:          {event.user}")
    print(f"  user_name:     {event.user_name}")
    print(f"  target_user:   {event.target_user}")
    print(f"  target_name:   {event.target_user_name}")
    print(f"  device:        {event.device}")
    print(f"  device_name:   {event.device_name}")
    print(f"  system_code:   {event.system_code}")
    print(f"  system_text:   {event.system_text}")
    print(f"  raw event:     {event.raw}")


def build_query_manager(args: argparse.Namespace) -> CommandSessionManager:
    """Build the manager used by query mode."""
    if not args.host or not args.account:
        raise ValueError("--host and --account are required in query mode")

    endpoint = PanelEndpoint(
        host=args.host,
        account=args.account,
        port=args.port,
        remote_key=args.remote_key,
        v31_compare_material=args.v31_material,
        panel_serial=args.panel_serial,
        user_code=args.user_code,
        passphrase=args.passphrase,
        v30_tail4=args.v30_tail4,
    )
    session_mode = SessionMode(args.session_type)
    session_profile = build_session_profile(
        session_mode,
        remote_key=args.remote_key or "",
        compare_material=args.v31_material or "",
        panel_serial=args.panel_serial or "",
        code=args.user_code or "",
        tail4=args.v30_tail4 or "",
        passphrase=args.passphrase or "",
    )
    return CommandSessionManager(endpoint, session_profile=session_profile)


async def async_listen_main(args: argparse.Namespace) -> int:
    """Run the new-core listener and print inbound events."""
    profile = (
        ListenerProfilePush(secure_passphrases=[args.passphrase])
        if args.passphrase
        else ListenerProfilePush()
    )
    listener = DMPPushListener(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        profile=profile,
    )

    def on_push(message: PushMessage) -> None:
        print_push_message(message)

    listener.register_callback(on_push)
    await listener.start()

    mode_label = "secure_s" if args.passphrase else "clear"
    print(
        f"Listening on {args.listen_host}:{args.listen_port} "
        f"in {mode_label} mode. Press Ctrl+C to stop."
    )

    try:
        await asyncio.Event().wait()
    finally:
        await listener.stop()

    return 0


async def async_main(args: argparse.Namespace) -> int:
    """Run the example against the selected session profile."""
    if args.mode == "listen":
        return await async_listen_main(args)

    manager = build_query_manager(args)

    try:
        if not args.skip_areas:
            area_transaction = await manager.submit(TransactionQueryAreas(args.area))
            print_area_transaction(area_transaction)

        if not args.skip_zones:
            zone_transaction = await manager.submit(TransactionQueryZones())
            print_zone_transaction(zone_transaction)
    finally:
        await manager.close()

    return 0


def main() -> int:
    """Entrypoint for the example script."""
    try:
        return asyncio.run(async_main(build_args()))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
