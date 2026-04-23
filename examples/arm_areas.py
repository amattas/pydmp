"""Arm one or more areas with a direct transaction example."""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_manager_from_args, print_transaction_wire_data, run_async_entrypoint
from pydmp.core import AreaControlReply, TransactionArmAreas


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Arm one or more areas with the new stateless core.")
    add_common_command_arguments(parser)
    parser.add_argument("--areas", required=True, nargs="+", help="One or more area numbers, such as --areas 1 2 3.")
    parser.add_argument("--bypass-faulted", action="store_true", help="Send the bypass-faulted arm flag.")
    parser.add_argument("--force-arm", action="store_true", help="Send the force-arm flag.")
    parser.add_argument("--instant", action="store_true", help="Send the instant arm flag.")
    parser.add_argument("--confirm-live-write", action="store_true", help="Required safety flag before sending a live arm command.")
    return parser


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    if not args.confirm_live_write:
        print("Refusing to send a live arm command without --confirm-live-write.")
        return 2

    manager = build_manager_from_args(args)

    try:
        transaction = await manager.submit(TransactionArmAreas(args.areas, bypass_faulted=args.bypass_faulted, force_arm=args.force_arm, instant=args.instant))
        reply = transaction.parsed_response
        if not isinstance(reply, AreaControlReply):
            raise ValueError("Arm-areas transaction completed without a parsed reply")

        print(f"command: {reply.command}")
        print(f"acknowledged: {reply.acknowledged}")
        print(f"detail: {reply.detail or '<none>'}")

        if args.show_raw:
            print_transaction_wire_data(transaction.wire_requests, transaction.wire_responses)
    finally:
        await manager.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 arm_areas.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
