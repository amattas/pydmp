"""Send the sensor-reset transaction with an explicit live-write guard."""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_manager_from_args, print_transaction_wire_data, run_async_entrypoint
from pydmp.core import SensorResetReply, TransactionSensorReset


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Run !E001 sensor reset with the new stateless core.")
    add_common_command_arguments(parser)
    parser.add_argument("--confirm-live-write", action="store_true", help="Required safety flag before sending a live sensor reset.")
    return parser


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    if not args.confirm_live_write:
        print("Refusing to send a live sensor reset without --confirm-live-write.")
        return 2

    manager = build_manager_from_args(args)

    try:
        transaction = await manager.submit(TransactionSensorReset())
        reply = transaction.parsed_response
        if not isinstance(reply, SensorResetReply):
            raise ValueError("Sensor-reset transaction completed without a parsed reply")

        print(f"acknowledged: {reply.acknowledged}")
        print(f"detail: {reply.detail or '<none>'}")

        if args.show_raw:
            print_transaction_wire_data(transaction.wire_requests, transaction.wire_responses)
    finally:
        await manager.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 sensor_reset.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
