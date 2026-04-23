"""Query the full visible profile table with a direct transaction example."""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_manager_from_args, normalize_name_for_display, print_section_heading, print_transaction_wire_data, run_async_entrypoint
from pydmp.core import ProfileReply, TransactionQueryProfiles


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Query the visible profile table with the new stateless core.")
    add_common_command_arguments(parser)
    return parser


def _format_area_list(values: tuple[int, ...]) -> str:
    if not values:
        return "-"
    return ",".join(f"{value:02d}" for value in values)


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    manager = build_manager_from_args(args)

    try:
        transaction = await manager.submit(TransactionQueryProfiles())
        reply = transaction.parsed_response
        if not isinstance(reply, ProfileReply):
            raise ValueError("Profile query transaction completed without a parsed reply")

        print(f"complete: {reply.complete}")
        print(f"profiles: {len(reply.profiles)}")
        print(f"raw replies: {len(reply.raw_replies)}")

        print()
        print("prof  arm/disarm        access            outgrp tail1 easyArm card+pin techUser name")
        print("----  ----------------  ----------------  ------ ----- ------- -------- -------- ----")
        for profile in reply.profiles:
            output_group = profile.output_group_number if profile.output_group_number is not None else "-"
            print(f"{profile.number:>4}  {_format_area_list(profile.arm_disarm_areas):16}  {_format_area_list(profile.access_areas):16}  {str(output_group):>6} {str(profile.tail_01 or '-'):>5} {('Y' if profile.easy_arm_disarm else 'N'):>7} {('Y' if profile.card_plus_pin else 'N'):>8} {('Y' if profile.technician_user else 'N'):>8} {normalize_name_for_display(profile.name)}")

        if args.show_raw:
            print_section_heading("Raw Replies")
            for index, raw_reply in enumerate(reply.raw_replies, start=1):
                print(f"reply {index}: {raw_reply.decode('ascii', errors='backslashreplace')}")
            print_transaction_wire_data(transaction.wire_requests, transaction.wire_responses)
    finally:
        await manager.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 query_profiles.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
