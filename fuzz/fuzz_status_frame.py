"""atheris target: the S3 status listener's frame handling on panel-pushed bytes.

Drives the same path as DMPStatusServer._handle_client without a socket: split the stream
on CR exactly as the listener does, hand each frame to _process_line (account extraction,
ACK, Z-body parse, dispatch), then run parse_s3_message on every dispatched message.

Contract: none of these raise. _handle_client swallows any exception by dropping the
panel connection (and every frame still buffered), so any exception here is a finding.
"""

import asyncio
import sys
from typing import Any

from pydmp.status_parser import parse_s3_message
from pydmp.status_server import DMPStatusServer, S3Message


class _Writer:
    def write(self, data: bytes) -> None:
        pass

    async def drain(self) -> None:
        pass


_LOOP = asyncio.new_event_loop()
_SERVER = DMPStatusServer()
_WRITER: Any = _Writer()
_MESSAGES: list[S3Message] = []
_SERVER.register_callback(_MESSAGES.append)


def TestOneInput(data: bytes) -> None:  # noqa: N802 - atheris entry-point name
    _MESSAGES.clear()
    buf = data
    while b"\r" in buf:
        line, buf = buf.split(b"\r", 1)
        if line:
            _LOOP.run_until_complete(_SERVER._process_line(line, _WRITER))
    for msg in _MESSAGES:
        parse_s3_message(msg)


def main() -> None:
    import atheris

    atheris.instrument_all()
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
