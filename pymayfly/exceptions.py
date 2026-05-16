"""
IPT framework exceptions.

All exceptions inherit from IPTError so callers can catch the
full family with a single except clause.
"""


class IPTError(Exception):
    """Base class for all pymayfly exceptions."""


class IPTBrokerError(IPTError):
    """Raised when a broker cannot issue or revoke a credential."""


class IPTExpiredCredentialError(IPTError):
    """Raised when a credential is used after its expiry."""


class IPTScopeError(IPTError):
    """Raised when a resource or action is outside the permitted scope."""


class IPTAuditError(IPTError):
    """Raised when the audit ledger cannot record a transaction."""
