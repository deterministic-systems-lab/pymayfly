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

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

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
    if name == "GCSBroker":
        from .providers.gcs import GCSBroker

        return GCSBroker
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
    "GCSBroker",
    # Exceptions
    "IPTError",
    "IPTBrokerError",
    "IPTExpiredCredentialError",
    "IPTScopeError",
    "IPTAuditError",
]

try:
    __version__ = _version("pymayfly")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"
__author__ = "Tristan McKinnon"
__license__ = "Apache-2.0"
