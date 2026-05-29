"""
pymayfly — Identity-Per-Transaction for regulated data pipelines.
Like a mayfly, these credentials live for exactly one transaction.


Quickstart::

    from pymayfly import IPTEnforcer, AWSSTSBroker, FileAuditLedger

    enforcer = IPTEnforcer(
        broker=AWSSTSBroker(role_arn="arn:aws:iam::123:role/IPTProcessor"),
        ledger=FileAuditLedger("/var/log/mayfly/audit.jsonl"),
    )

    @enforcer.protect(
        resource_from=lambda e: f"arn:aws:s3:::my-bucket/{e['key']}",
        action="read",
    )
    def handler(event, context, *, creds):
        ...

Research::

    McKinnon, T. (2026). Zero-Trust Data Engineering: A Reference
    Architecture for Serverless, FedRAMP-High Healthcare Pipelines.
    IEEE BigDataSecurity 2026.
"""

from .core.audit import AuditLedger, ConsoleAuditLedger, FileAuditLedger
from .core.broker import EphemeralCredential, IdentityBroker
from .core.enforce import IPTEnforcer, ipt_handler
from .core.provenance import ProvenanceRecord
from .core.scope import transaction_scope
from .exceptions import (
    IPTAuditError,
    IPTBrokerError,
    IPTError,
    IPTExpiredCredentialError,
    IPTScopeError,
)

# Providers are imported lazily to avoid hard dependencies.
# Use: from pymayfly.providers.aws_sts import AWSSTSBroker
# Or:  from pymayfly import AWSSTSBroker  (raises ImportError if boto3 missing)

def __getattr__(name: str) -> object:
    if name == "AWSSTSBroker":
        from .providers.aws_sts import AWSSTSBroker

        return AWSSTSBroker
    if name == "AzureBlobBroker":
        from .providers.azure_blob import AzureBlobBroker

        return AzureBlobBroker
    raise AttributeError(f"module 'pymayfly' has no attribute {name!r}")


__all__ = [
    # Core abstractions
    "IdentityBroker",
    "EphemeralCredential",
    "AuditLedger",
    "ConsoleAuditLedger",
    "FileAuditLedger",
    "ProvenanceRecord",
    # Execution primitives
    "transaction_scope",
    "ipt_handler",
    "IPTEnforcer",
    # Providers (lazy)
    "AWSSTSBroker",
    "AzureBlobBroker",
    # Exceptions
    "IPTError",
    "IPTBrokerError",
    "IPTExpiredCredentialError",
    "IPTScopeError",
    "IPTAuditError",
]

__version__ = "0.1.0"
__author__ = "Tristan McKinnon"
__license__ = "Apache-2.0"
