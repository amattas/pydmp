"""Query outputs with the beginner-friendly client.

This example shows the most important `?WQ` choices:

- where to start
- which namespace to query
- whether unnamed rows should be filtered out
- whether to print the filtered results or every raw row the panel returned
"""

from __future__ import annotations

import argparse

from _example_support import add_common_command_arguments, build_client_from_args, normalize_name_for_display, print_section_heading, run_async_entrypoint


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for this example."""
    parser = argparse.ArgumentParser(description="Query outputs with the new stateless core client.")
    add_common_command_arguments(parser)
    parser.add_argument("--start-selector", default="001", help="Starting selector such as 001, D01, F01, or G01.")
    parser.add_argument("--namespace", choices=["numeric", "D", "F", "G"], help="Selector family to keep in the returned records.")
    parser.add_argument("--include-unnamed", action="store_true", help="Keep blank-name rows and '* UNUSED *' rows in the returned record set.")
    parser.add_argument("--show-all-records", action="store_true", help="Print every raw row returned by the query, not just the filtered record set.")
    parser.add_argument("--max-pages", type=int, default=200, help="Hard stop for page collection. The default is intentionally generous.")
    return parser


async def async_main() -> int:
    """Run the example."""
    args = build_parser().parse_args()
    client = build_client_from_args(args)

    try:
        reply = await client.query_outputs(start_selector=args.start_selector, namespace=args.namespace, named_only=not args.include_unnamed, max_pages=args.max_pages)
        records = reply.all_records if args.show_all_records else reply.records

        print(f"complete: {reply.complete}")
        print(f"namespace: {reply.namespace}")
        print(f"named_only: {reply.named_only}")
        print(f"returned records: {len(reply.records)}")
        print(f"all raw records: {len(reply.all_records or [])}")
        print(f"raw replies: {len(reply.raw_replies)}")

        print()
        print("selector namespace status name")
        print("-------- --------- ------ ----")
        for record in records:
            print(f"{record.selector:>8} {record.namespace:>9} {record.status:^6} {normalize_name_for_display(record.name)}")

        if args.show_raw:
            print_section_heading("Raw Replies")
            for index, raw_reply in enumerate(reply.raw_replies, start=1):
                print(f"reply {index}: {raw_reply.decode('ascii', errors='backslashreplace')}")
    finally:
        await client.close()

    return 0


def main() -> int:
    """Synchronous entrypoint used by `python3 query_outputs.py`."""
    return run_async_entrypoint(async_main)


if __name__ == "__main__":
    raise SystemExit(main())
