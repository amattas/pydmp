"""Query one zone-settings record with a direct transaction example."""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_manager_from_args, normalize_name_for_display, print_transaction_wire_data, run_async_entrypoint
from pydmp.core import TransactionQueryZoneSettings, ZoneSettingsReply


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Query one zone-settings record with the new stateless core.")
    add_common_command_arguments(parser)
    parser.add_argument("--zone", required=True, help="Zone number to query, from 1 to 999.")
    return parser


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    manager = build_manager_from_args(args)

    try:
        transaction = await manager.submit(TransactionQueryZoneSettings(args.zone))
        reply = transaction.parsed_response
        if not isinstance(reply, ZoneSettingsReply):
            raise ValueError("Zone-settings transaction completed without a parsed reply")

        print(f"requested zone: {reply.requested_zone}")
        print(f"found: {reply.found}")
        print(f"short_default: {reply.short_default}")
        print(f"records_on_page: {len(reply.records)}")
        print(f"has_terminal_marker: {reply.has_terminal_marker}")

        if reply.zone is None:
            print("The requested zone was not present in the reply.")
        else:
            zone = reply.zone
            print(f"number: {zone.number}")
            print(f"type_code: {zone.type_code}")
            print(f"area: {zone.area}")
            print(f"display_option: {zone.display_option}")
            print(f"entry_delay_number: {zone.entry_delay_number}")
            print(f"pir_pulse_count: {zone.pir_pulse_count}")
            print(f"pir_sensitivity: {zone.pir_sensitivity}")
            print(f"reference8: {zone.reference8}")
            print(f"reference10: {zone.reference10}")
            print(f"disarmed_open_action: {zone.disarmed_open_action}")
            print(f"disarmed_open_output: {zone.disarmed_open_output}")
            print(f"disarmed_open_output_mode: {zone.disarmed_open_output_mode}")
            print(f"disarmed_short_action: {zone.disarmed_short_action}")
            print(f"disarmed_short_output: {zone.disarmed_short_output}")
            print(f"disarmed_short_output_mode: {zone.disarmed_short_output_mode}")
            print(f"armed_open_action: {zone.armed_open_action}")
            print(f"armed_open_output: {zone.armed_open_output}")
            print(f"armed_open_output_mode: {zone.armed_open_output_mode}")
            print(f"armed_short_action: {zone.armed_short_action}")
            print(f"armed_short_output: {zone.armed_short_output}")
            print(f"armed_short_output_mode: {zone.armed_short_output_mode}")
            print(f"name_prefix: {zone.name_prefix or '<none>'}")
            print(f"name: {normalize_name_for_display(zone.name)}")

        if args.show_raw:
            print_transaction_wire_data(transaction.wire_requests, transaction.wire_responses)
    finally:
        await manager.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 query_zone_settings.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
