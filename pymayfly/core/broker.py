"""
Identity broker interface for the Identity-Per-Transaction protocol.

Every provider must implement IdentityBroker. The library ships with:
  - AWSSTSBroker (pymayfly[aws])

Planned providers:
  - VaultBroker
  - SupabaseJWTBroker
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EphemeralCredential:
    """
    A credential scoped to exactly one resource for one transaction.

    Attributes:
        token:          Provider-specific credential object.
                        AWS STS: dict with AccessKeyId / SecretAccessKey / SessionToken.
                        Vault: dict with keys for the target platform.
                        JWT brokers: signed token string.
        expiry:         Unix timestamp at which the credential expires.
        scope:          Human-readable description of what the credential grants.
        transaction_id: UUID linking this credential to its ProvenanceRecord.
        lease_id:       Provider-specific revocation handle. Vault populates this;
                        AWS STS does not support explicit revocation.
        metadata:       Arbitrary provider metadata for audit or debugging.
    """

    token: Any
    expiry: int
    scope: str
    transaction_id: str
    lease_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return int(time.time()) >= self.expiry

    @property
    def ttl(self) -> int:
        """Seconds remaining before expiry. 0 if already expired."""
        return max(0, self.expiry - int(time.time()))

    def __repr__(self) -> str:
        return (
            f"EphemeralCredential("
            f"transaction_id={self.transaction_id!r}, "
            f"scope={self.scope!r}, "
            f"ttl={self.ttl}s, "
            f"expired={self.is_expired})"
        )


class IdentityBroker(ABC):
    """
    Abstract base class for all IPT identity brokers.

    A broker issues EphemeralCredentials scoped to a single resource
    and action for the duration of one transaction. Implementations
    must enforce:

      1. Credentials expire at or before the transaction boundary.
      2. Scope is the narrowest possible for the requested operation.
      3. No credential is reused across transactions.

    Providers that support explicit revocation should implement revoke().
    Providers that cannot revoke (e.g. AWS STS) should document the
    TTL as the security backstop and rely on resource destruction
    (object deletion) as the secondary control.
    """

    @abstractmethod
    def issue(
        self,
        transaction_id: str,
        resource: str,
        action: str,
    ) -> EphemeralCredential:
        """
        Issue a credential scoped to exactly one resource and action.

        Args:
            transaction_id: UUID for this transaction. Must be unique.
            resource:       Full resource identifier (ARN, URI, table name).
            action:         Requested operation ("read", "write", "delete",
                            or provider-specific action string).

        Returns:
            EphemeralCredential valid for exactly this transaction.

        Raises:
            IPTBrokerError: If the credential cannot be issued.
        """
        ...

    @abstractmethod
    def revoke(self, credential: EphemeralCredential) -> None:
        """
        Explicitly revoke a credential before its TTL expires.

        Providers that cannot revoke (e.g. AWS STS) should log the
        no-op and document it. Do not raise.

        Args:
            credential: The credential to revoke.
        """
        ...

    @abstractmethod
    def blast_radius(self, credential: EphemeralCredential) -> str:
        """
        Describe what a compromised credential exposes.

        Used in audit records and observability. Should be as specific
        as possible — prefer "Single S3 object: s3://bucket/key" over
        "One object."

        Args:
            credential: The issued credential.

        Returns:
            Human-readable blast radius description.
        """
        ...
