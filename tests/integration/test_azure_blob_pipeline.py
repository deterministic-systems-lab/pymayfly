import json

from pymayfly import FileAuditLedger, transaction_scope
from pymayfly.providers.azure_blob import AzureBlobBroker

ACCOUNT_URL = "https://acct.blob.core.windows.net"


class _StubCredential:
    """Minimal token credential; the SDK only checks for get_token, and
    get_user_delegation_key is monkeypatched so it is never actually called."""

    def get_token(self, *scopes, **kwargs):  # pragma: no cover - never invoked
        raise AssertionError("network token request should not happen in tests")


def test_azure_blob_broker_issues_scoped_credentials_with_file_audit(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.get_user_delegation_key",
        lambda self, start, expiry: object(),
    )
    monkeypatch.setattr(
        "azure.storage.blob.generate_blob_sas",
        lambda **kwargs: "sv=2024-01-01&sig=fake-signature",
    )

    broker = AzureBlobBroker(account_url=ACCOUNT_URL, credential=_StubCredential())

    audit_path = tmp_path / "audit.jsonl"
    resource = "az://dirty-zone/patient-001.parquet"

    with transaction_scope(
        broker=broker,
        resource=resource,
        action="read",
        ledger=FileAuditLedger(audit_path),
        transaction_id="txn-azure-integration",
    ) as creds:
        assert creds.token["sas_token"] == "sv=2024-01-01&sig=fake-signature"
        assert creds.scope == f"read:{resource}"
        assert creds.metadata["container"] == "dirty-zone"
        assert creds.metadata["permission"] == "read"

    audit_records = [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event"] for record in audit_records] == ["OPEN", "CLOSE"]
    assert audit_records[0]["blast_radius"] == f"Single Azure blob: read:{resource}"
