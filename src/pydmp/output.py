"""Historic `pydmp.output` import path routed to the wrapper implementation."""

from .wrapper.output import Output, OutputSync

__all__ = ["Output", "OutputSync"]
