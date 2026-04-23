"""Query all areas with the beginner-friendly client.

This is the smallest good example for the new command core.
It shows the usual pattern:

1. build a client
2. run one named query
3. print the parsed result
4. optionally print raw wire traffic
"""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_client_from_args, normalize_name_for_display, print_section_heading, run_async_entrypoint


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Query all areas with the new stateless core client.")
    add_common_command_arguments(parser)
    return parser


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    client = build_client_from_args(args)

    try:
        reply = await client.query_areas()

        print(f"complete: {reply.complete}")
        print(f"areas: {len(reply.areas)}")
        print(f"raw replies: {len(reply.raw_replies)}")

        print()
        print("area  state unknown scheduleActive lateToClose name")
        print("----  ----- ------- -------------- ----------- ----")
        for area in reply.areas:
            print(f"{area.number:>4}  {area.state:^5} {area.unknown:^7} {area.schedule_active:^14} {area.late_to_close:^11} {normalize_name_for_display(area.name)}")

        if args.show_raw:
            print_section_heading("Raw Replies")
            for index, raw_reply in enumerate(reply.raw_replies, start=1):
                print(f"reply {index}: {raw_reply.decode('ascii', errors='backslashreplace')}")
    finally:
        await client.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 query_areas.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
