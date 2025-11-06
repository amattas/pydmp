import pytest

from pydmp.exceptions import DMPInvalidParameterError
from pydmp.output import Output, OutputSync


class _P:
    async def _send_command(self, *a, **k):
        return "ACK"


@pytest.mark.asyncio
async def test_output_constructor_update_state_and_formatted():
    with pytest.raises(DMPInvalidParameterError):
        Output(_P(), 0)

    o = Output(_P(), 12, name="Relay")
    o.update_state("ON", name="R12")
    assert o.name == "R12" and o.state == "ON"
    assert o.formatted_number == "012"


def test_output_sync_accessors_and_repr():
    class SyncPanel:
        def _run(self, coro):
            import asyncio

            return asyncio.get_event_loop().run_until_complete(coro)

    o = Output(_P(), 3, name="R3")
    s = OutputSync(o, SyncPanel())
    assert s.number == 3 and s.name == "R3" and s.state in {"unknown", "", "ON", "OF"}
    assert isinstance(repr(s), str) and "OutputSync" in repr(s)
