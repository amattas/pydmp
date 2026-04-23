"""Exceptions used by the stateless core.

The core uses two main error families:

- command/session errors for request/response work
- listener errors for inbound push handling

Keeping those families separate makes it easier for callers to decide what
kind of recovery or logging is appropriate.
"""


class CommandSessionError(Exception):
    """Base error for session-managed command execution."""


class ListenerError(Exception):
    """Base error for push-listener operation."""


# Listener-side errors.
class ListenerConfigurationError(ListenerError):
    """Raised when a listener profile is missing required configuration."""


class ListenerProtocolError(ListenerError):
    """Raised when inbound push traffic is malformed for the active profile."""


# Command/session-side errors.
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
    """Raised when a transaction-specific parser cannot decode a reply.

    This is kept separate from transport/session failures so callers can tell
    the difference between "the panel interaction failed" and "the reply was
    received but our parser did not understand it."
    """
