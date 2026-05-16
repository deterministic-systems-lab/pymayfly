"""
Provenance-Per-Record (PPR) layer for the IPT protocol.

Every transaction produces a ProvenanceRecord that is written to the
AuditLedger before the transaction opens and updated when it closes
or fails. This satisfies FedRAMP AU-2 (Audit Events) and AU-3
(Content of Audit Records).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

TransactionStatus = Literal["open", "closed", "failed"]


@dataclass
class ProvenanceRecord:
    """
    Immutable audit record for a single IPT transaction.

    Fields mirror FedRAMP AU-3 required content:
      - Who:   transaction_id (non-human identity, scoped per transaction)
      - What:  action, resource
      - When:  issued_at, closed_at
      - Where: blast_radius (scope of access)
      - Result: status, error
    """

    transaction_id: str
    resource: str
    action: str
    issued_at: int
    blast_radius: str
    status: TransactionStatus = "open"
    closed_at: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int | None:
        """Transaction duration in milliseconds. None if still open."""
        if self.closed_at is None:
            return None
        return (self.closed_at - self.issued_at) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "resource": self.resource,
            "action": self.action,
            "issued_at": self.issued_at,
            "closed_at": self.closed_at,
            "blast_radius": self.blast_radius,
            "status": self.status,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    def sha256(self) -> str:
        """
        SHA-256 hash of the record for tamper-evident logging.
        Matches the cryptographic lineage approach in the IPT paper.
        """
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()
