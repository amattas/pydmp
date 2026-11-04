"""atheris target: DMPProtocol.decode_response on raw panel reply bytes.

Contract (decode_response docstring): it returns a decoded value or None and raises only
DMPInvalidResponseError. Any other exception is a finding.
"""

import contextlib
import sys

from pydmp.exceptions import DMPInvalidResponseError
from pydmp.protocol import DMPProtocol

# A remote key long enough to feed the system seed, so user-code decryption runs that path too.
_PROTOCOL = DMPProtocol("1", "0123456789ABCDEF")


def test_one_input(data: bytes) -> None:
    with contextlib.suppress(DMPInvalidResponseError):
        _PROTOCOL.decode_response(data)


def main() -> None:
    import atheris

    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
