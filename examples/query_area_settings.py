"""Query one area-settings record with a direct transaction example.

This example is here on purpose even though the client also exposes
`query_area_settings()`. The new core is transaction-based, so it helps to have
one small script that shows the direct manager workflow clearly.
"""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_manager_from_args, normalize_name_for_display, print_transaction_wire_data, run_async_entrypoint
from pydmp.core import AreaSettingsReply, TransactionQueryAreaSettings


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Query one area-settings record with the new stateless core.")
    add_common_command_arguments(parser)
    parser.add_argument("--area", required=True, help="Area number to query, from 1 to 32.")
    return parser


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    manager = build_manager_from_args(args)

    try:
        transaction = await manager.submit(TransactionQueryAreaSettings(args.area))
        reply = transaction.parsed_response
        if not isinstance(reply, AreaSettingsReply):
            raise ValueError("Area-settings transaction completed without a parsed reply")

        print(f"requested area: {reply.requested_area}")
        print(f"found: {reply.found}")

        if reply.area is None:
            print("The requested area was not present in the reply.")
        else:
            area = reply.area
            print(f"number: {area.number}")
            print(f"account: {area.account}")
            print(f"auto_arm: {area.auto_arm}")
            print(f"bad_zones: {area.bad_zones}")
            print(f"auto_disarm: {area.auto_disarm}")
            print(f"armed_output: {area.armed_output}")
            print(f"bank_saf: {area.bank_saf}")
            print(f"common: {area.common}")
            print(f"dual_authority: {area.dual_authority}")
            print(f"arm_first: {area.arm_first}")
            print(f"late_output: {area.late_output}")
            print(f"late_arm_delay: {area.late_arm_delay}")
            print(f"oc_reports: {area.oc_reports}")
            print(f"burg_bell_output: {area.burg_bell_output}")
            print(f"card_plus_pin: {area.card_plus_pin}")
            print(f"name: {normalize_name_for_display(area.name)}")

        if args.show_raw:
            print_transaction_wire_data(transaction.wire_requests, transaction.wire_responses)
    finally:
        await manager.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 query_area_settings.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
