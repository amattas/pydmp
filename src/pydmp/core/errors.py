"""Exceptions used by the stateless core."""


class CommandSessionError(Exception):
    """Base error for session-managed command execution."""


class ListenerError(Exception):
    """Base error for push-listener operation."""


class ListenerConfigurationError(ListenerError):
    """Raised when a listener profile is missing required configuration."""


class ListenerProtocolError(ListenerError):
    """Raised when inbound push traffic is malformed for the active profile."""


class SessionClosedError(CommandSessionError):
    """Raised when work is submitted after the manager is closed."""


class SessionConnectError(CommandSessionError):
    """Raised when a TCP connection cannot be established."""


class SessionHandshakeError(CommandSessionError):
    """Raised when session startup fails at the protocol level."""


class SessionTimeoutError(CommandSessionError):
    """Raised when a required reply does not arrive in time."""


class SessionProtocolError(CommandSessionError):
    """Raised when a reply is malformed for the active session mode."""


class SessionProfileNotImplementedError(CommandSessionError):
    """Raised by scaffolded session profiles that are not implemented yet."""


class TransactionParseError(Exception):
    """Raised when a transaction-specific parser cannot decode a reply."""
