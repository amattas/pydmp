"""Query the programmer lockout code with a direct transaction example."""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_manager_from_args, print_transaction_wire_data, run_async_entrypoint
from pydmp.core import LockoutCodeReply, TransactionQueryLockoutCode


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Query the programmer lockout code with the new stateless core.")
    add_common_command_arguments(parser)
    return parser


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    manager = build_manager_from_args(args)

    try:
        transaction = await manager.submit(TransactionQueryLockoutCode())
        reply = transaction.parsed_response
        if not isinstance(reply, LockoutCodeReply):
            raise ValueError("Lockout-code transaction completed without a parsed reply")

        print(f"code: {reply.code}")
        print(f"numeric_value: {reply.numeric_value}")
        print(f"is_null: {reply.is_null}")
        print(f"trailing_payload: {reply.trailing_payload or '<none>'}")

        if args.show_raw:
            print_transaction_wire_data(transaction.wire_requests, transaction.wire_responses)
    finally:
        await manager.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 query_lockout_code.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
