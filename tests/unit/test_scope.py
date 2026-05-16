import pytest

from pymayfly.core.audit import FileAuditLedger
from pymayfly.core.scope import transaction_scope
from pymayfly.exceptions import IPTBrokerError, IPTExpiredCredentialError


def test_scope_yields_credential(broker):
    with transaction_scope(broker, "s3://bucket/key", "read") as creds:
        assert creds is not None
        assert creds.transaction_id is not None


def test_scope_revokes_on_exit(broker):
    with transaction_scope(broker, "s3://bucket/key", "read") as creds:
        txn_id = creds.transaction_id

    revoked_ids = [c.transaction_id for c in broker.revoked]
    assert txn_id in revoked_ids


def test_scope_revokes_on_exception(broker):
    with pytest.raises(ValueError):
        with transaction_scope(broker, "s3://bucket/key", "read") as creds:
            txn_id = creds.transaction_id
            raise ValueError("processing failed")

    revoked_ids = [c.transaction_id for c in broker.revoked]
    assert txn_id in revoked_ids


def test_scope_uses_provided_transaction_id(broker):
    with transaction_scope(
        broker, "s3://bucket/key", "read", transaction_id="my-known-id"
    ) as creds:
        assert creds.transaction_id == "my-known-id"


def test_scope_raises_on_expired_credential(expired_broker):
    with pytest.raises(IPTExpiredCredentialError):
        with transaction_scope(expired_broker, "s3://bucket/key", "read"):
            pass


def test_scope_raises_on_broker_failure(failing_broker):
    with pytest.raises(IPTBrokerError):
        with transaction_scope(failing_broker, "s3://bucket/key", "read"):
            pass


def test_scope_writes_to_file_ledger(broker, tmp_path):
    log_file = tmp_path / "audit.jsonl"
    ledger = FileAuditLedger(log_file)

    with transaction_scope(broker, "s3://bucket/key", "read", ledger=ledger):
        pass

    lines = log_file.read_text().strip().split("\n")
    # open + close = 2 records
    assert len(lines) == 2
    assert '"OPEN"' in lines[0]
    assert '"CLOSE"' in lines[1]


def test_scope_records_failure_in_ledger(broker, tmp_path):
    log_file = tmp_path / "audit.jsonl"
    ledger = FileAuditLedger(log_file)

    with pytest.raises(RuntimeError):
        with transaction_scope(broker, "s3://bucket/key", "read", ledger=ledger):
            raise RuntimeError("downstream failure")

    lines = log_file.read_text().strip().split("\n")
    assert '"OPEN"' in lines[0]
    assert '"FAIL"' in lines[1]
