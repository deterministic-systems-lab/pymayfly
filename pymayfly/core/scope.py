"""
TransactionScope: the core IPT execution primitive.

Every operation on a protected resource must occur inside a
transaction_scope. The scope:

  1. Issues a scoped EphemeralCredential via the broker.
  2. Writes an open ProvenanceRecord to the ledger.
  3. Yields the credential to the caller.
  4. Revokes the credential on exit (whether or not the body raised).
  5. Writes a close or failure ProvenanceRecord to the ledger.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager

from ..exceptions import IPTExpiredCredentialError
from .audit import AuditLedger, ConsoleAuditLedger
from .broker import EphemeralCredential, IdentityBroker
from .provenance import ProvenanceRecord


@contextmanager
def transaction_scope(
    broker: IdentityBroker,
    resource: str,
    action: str,
    ledger: AuditLedger | None = None,
    transaction_id: str | None = None,
) -> Generator[EphemeralCredential, None, None]:
    """
    Context manager that enforces Identity-Per-Transaction.

    Issues a credential scoped to exactly one resource and action,
    yields it to the caller, then revokes it on exit regardless of
    whether the body raised.

    Args:
        broker:         IdentityBroker implementation to use.
        resource:       Full resource identifier (ARN, URI, path).
        action:         Requested action ("read", "write", "delete").
        ledger:         AuditLedger to record the transaction.
                        Defaults to ConsoleAuditLedger if None.
        transaction_id: Override the generated UUID. Useful for
                        correlating with upstream transaction IDs.

    Yields:
        EphemeralCredential scoped to the requested resource and action.

    Raises:
        IPTExpiredCredentialError: If the credential expires before
                                   the scope exits.
        IPTBrokerError:            If the broker cannot issue a credential.

    Example::

        with transaction_scope(broker, resource="s3://bucket/key", action="read") as creds:
            client = build_s3_client(creds)
            data = client.get_object(...)
    """
    _ledger = ledger or ConsoleAuditLedger()
    txn_id = transaction_id or str(uuid.uuid4())

    credential = broker.issue(txn_id, resource, action)

    record: ProvenanceRecord | None = None

    try:
        record = ProvenanceRecord(
            transaction_id=txn_id,
            resource=resource,
            action=action,
            issued_at=int(time.time()),
            blast_radius=broker.blast_radius(credential),
        )

        _ledger.open_transaction(record)

        if credential.is_expired:
            raise IPTExpiredCredentialError(
                f"Credential expired immediately after issuance: {credential}"
            )
        yield credential
    except Exception as exc:
        if record is not None:
            _ledger.record_failure(record, str(exc))
        raise
    finally:
        broker.revoke(credential)
        if record is not None and record.status == "open":
            _ledger.close_transaction(record)
