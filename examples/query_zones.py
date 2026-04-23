"""Query the full area and zone snapshot with the beginner-friendly client."""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_client_from_args, normalize_name_for_display, print_section_heading, run_async_entrypoint


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Query all areas and zones with the new stateless core client.")
    add_common_command_arguments(parser)
    return parser


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    client = build_client_from_args(args)

    try:
        reply = await client.query_zones()

        print(f"complete: {reply.complete}")
        print(f"areas: {len(reply.areas)}")
        print(f"zones: {len(reply.zones)}")
        print(f"raw replies: {len(reply.raw_replies)}")

        print()
        print("area  state unknown scheduleActive lateToClose name")
        print("----  ----- ------- -------------- ----------- ----")
        for area in reply.areas:
            print(f"{area.number:>4}  {area.state:^5} {area.unknown:^7} {area.schedule_active:^14} {area.late_to_close:^11} {normalize_name_for_display(area.name)}")

        print()
        print("zone  area  status name")
        print("----  ----  ------ ----")
        for zone in reply.zones:
            print(f"{zone.number:>4}  {zone.area_number:>4}  {zone.status:^6} {normalize_name_for_display(zone.name)}")

        if args.show_raw:
            print_section_heading("Raw Replies")
            for index, raw_reply in enumerate(reply.raw_replies, start=1):
                print(f"reply {index}: {raw_reply.decode('ascii', errors='backslashreplace')}")
    finally:
        await client.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 query_zones.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
