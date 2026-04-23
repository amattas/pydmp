"""Query the full visible user table with a direct transaction example."""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_manager_from_args, normalize_name_for_display, print_section_heading, print_transaction_wire_data, run_async_entrypoint
from pydmp.core import TransactionQueryUsers, UserReply


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Query the visible user table with the new stateless core.")
    add_common_command_arguments(parser)
    return parser


def _format_profiles(profiles: tuple[str | None, str | None, str | None, str | None]) -> str:
    return ",".join(value or "-" for value in profiles)


def _format_flags(reply_flags) -> str:
    if reply_flags is None:
        return "---"
    return f"{'A' if reply_flags.active else '-'}{'1' if reply_flags.authority_1 else '-'}{'T' if reply_flags.temporary else '-'}"


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    manager = build_manager_from_args(args)

    try:
        transaction = await manager.submit(TransactionQueryUsers())
        reply = transaction.parsed_response
        if not isinstance(reply, UserReply):
            raise ValueError("User query transaction completed without a parsed reply")

        print(f"complete: {reply.complete}")
        print(f"users: {len(reply.users)}")
        print(f"raw replies: {len(reply.raw_replies)}")

        print()
        print("user  code          pin     profiles       end      start    flags name")
        print("----  ------------  ------  -------------  -------  -------  ----- ----")
        for user in reply.users:
            print(f"{user.number:>4}  {user.code:12}  {user.pin:6}  {_format_profiles(user.profiles):13}  {(user.end_date or '------'):7}  {(user.start_date or '------'):7}  {_format_flags(user.flags):5} {normalize_name_for_display(user.name)}")

        if args.show_raw:
            print_section_heading("Raw Replies")
            for index, raw_reply in enumerate(reply.raw_replies, start=1):
                print(f"reply {index}: {raw_reply.decode('ascii', errors='backslashreplace')}")
            print_transaction_wire_data(transaction.wire_requests, transaction.wire_responses)
    finally:
        await manager.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 query_users.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
