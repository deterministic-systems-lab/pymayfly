import json
from datetime import datetime

from google.auth import downscoped
from google.auth.credentials import AnonymousCredentials

from pymayfly import FileAuditLedger, transaction_scope
from pymayfly.providers.gcs import GCSBroker


def test_gcs_broker_issues_scoped_credentials_with_file_audit(tmp_path, monkeypatch):
    def fake_refresh(self, request):
        self.token = "downscoped-token-abc"
        self.expiry = datetime(2030, 1, 1)
    monkeypatch.setattr(downscoped.Credentials, "refresh", fake_refresh)

    broker = GCSBroker(
        target_principal="ipt@my-project.iam.gserviceaccount.com",
        source_credentials=AnonymousCredentials(),
    )

    audit_path = tmp_path / "audit.jsonl"
    resource = "gs://dirty-zone/patient-001.parquet"

    with transaction_scope(
        broker=broker,
        resource=resource,
        action="read",
        ledger=FileAuditLedger(audit_path),
        transaction_id="txn-gcs-integration",
    ) as creds:
        assert creds.token["access_token"] == "downscoped-token-abc"
        assert creds.scope == f"read:{resource}"
        assert creds.metadata["role"] == "roles/storage.objectViewer"

    audit_records = [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event"] for record in audit_records] == ["OPEN", "CLOSE"]
    assert audit_records[0]["blast_radius"] == f"Single GCS object: read:{resource}"
