"""Protocol-level constants for the DMP transport and framing."""

# Networking
DEFAULT_PORT = 2011
RATE_LIMIT_SECONDS = 0.3

# Framing
MESSAGE_TERMINATOR = "\r"
MESSAGE_PREFIX = "@"
RESPONSE_DELIMITER = "\x02"
ZONE_DELIMITER = "\x1e"

