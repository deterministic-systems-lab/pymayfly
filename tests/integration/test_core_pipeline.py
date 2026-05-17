import json

import pytest

from pymayfly import FileAuditLedger, IPTEnforcer, transaction_scope


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_context_manager_records_successful_transaction_end_to_end(broker, tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    ledger = FileAuditLedger(audit_path)

    with transaction_scope(
        broker=broker,
        resource="s3://dirty-zone/patient-001.parquet",
        action="read",
        ledger=ledger,
        transaction_id="txn-integration-success",
    ) as creds:
        assert creds.scope == "read:s3://dirty-zone/patient-001.parquet"

    records = _read_jsonl(audit_path)

    assert [record["event"] for record in records] == ["OPEN", "CLOSE"]
    assert [record["status"] for record in records] == ["open", "closed"]
    assert {record["transaction_id"] for record in records} == {"txn-integration-success"}
    assert records[0]["resource"] == "s3://dirty-zone/patient-001.parquet"
    assert records[1]["duration_ms"] is not None
    assert broker.revoked[0].transaction_id == "txn-integration-success"


def test_enforcer_decorator_records_failure_and_revokes_credential(broker, tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    enforcer = IPTEnforcer(broker=broker, ledger=FileAuditLedger(audit_path))

    @enforcer.protect(
        resource_from=lambda event: f"arn:aws:s3:::{event['bucket']}/{event['key']}",
        action="write",
    )
    def process(event, *, creds):
        assert creds.scope == "write:arn:aws:s3:::clean-zone/patient-001.parquet"
        raise RuntimeError("downstream write failed")

    with pytest.raises(RuntimeError, match="downstream write failed"):
        process({"bucket": "clean-zone", "key": "patient-001.parquet"})

    records = _read_jsonl(audit_path)

    assert [record["event"] for record in records] == ["OPEN", "FAIL"]
    assert records[1]["status"] == "failed"
    assert records[1]["error"] == "downstream write failed"
    assert records[1]["resource"] == "arn:aws:s3:::clean-zone/patient-001.parquet"
    assert len(broker.revoked) == 1
