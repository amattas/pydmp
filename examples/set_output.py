"""Set one output selector with a direct transaction example.

This example uses `CommandSessionManager` directly instead of `CorePanelClient`
so it can show the raw request and reply recorded on the transaction object.

For safety, the script refuses to send a live write unless you pass
`--confirm-live-write`.
"""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_manager_from_args, print_transaction_wire_data, run_async_entrypoint
from pydmp.core import OutputControlReply, TransactionSetOutput


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Set one output selector with the new stateless core.")
    add_common_command_arguments(parser)
    parser.add_argument("--output", required=True, help="Selector to write, such as 1, 580, or D01.")
    parser.add_argument("--mode", required=True, help="Mode byte or alias, such as O, P, S, M, off, pulse, or on.")
    parser.add_argument("--confirm-live-write", action="store_true", help="Required safety flag before a live output write is sent.")
    return parser


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    if not args.confirm_live_write:
        print("Refusing to send a live output write without --confirm-live-write.")
        print("Poll outputs first and limit writes to selectors the panel already reported as valid.")
        return 2

    manager = build_manager_from_args(args)

    try:
        transaction = await manager.submit(TransactionSetOutput(args.output, args.mode))
        reply = transaction.parsed_response
        if not isinstance(reply, OutputControlReply):
            raise ValueError("Set-output transaction completed without a parsed reply")

        print(f"selector: {reply.selector}")
        print(f"mode: {reply.mode}")
        print(f"acknowledged: {reply.acknowledged}")
        print(f"detail: {reply.detail or '<none>'}")

        if args.show_raw:
            print_transaction_wire_data(transaction.wire_requests, transaction.wire_responses)
    finally:
        await manager.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 set_output.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
