"""Exceptions for PyDMP."""


class DMPError(Exception):
    """Base exception for DMP errors."""


class DMPConnectionError(DMPError):
    """Connection-related errors."""


class DMPAuthenticationError(DMPConnectionError):
    """Authentication failed."""


class DMPTimeoutError(DMPConnectionError):
    """Operation timed out."""


class DMPProtocolError(DMPError):
    """Protocol-level errors."""


class DMPInvalidResponseError(DMPProtocolError):
    """Invalid or unexpected response from panel."""


class DMPCommandError(DMPError):
    """Command execution errors."""


class DMPCommandNAKError(DMPCommandError):
    """Command was rejected by panel (NAK response)."""


class DMPInvalidParameterError(DMPError):
    """Invalid parameter provided."""


class DMPAreaError(DMPError):
    """Area-related errors."""


class DMPZoneError(DMPError):
    """Zone-related errors."""


class DMPOutputError(DMPError):
    """Output-related errors."""
