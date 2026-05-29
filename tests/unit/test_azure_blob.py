import time
from datetime import timedelta

import pytest
from azure.storage.blob import BlobSasPermissions

from pymayfly.core.broker import EphemeralCredential
from pymayfly.exceptions import IPTBrokerError, IPTScopeError
from pymayfly.providers.azure_blob import AzureBlobBroker

ACCOUNT_URL = "https://acct.blob.core.windows.net"


class _StubCredential:
    """Minimal token credential; the SDK only checks for get_token, and
    get_user_delegation_key is monkeypatched so it is never actually called."""

    def get_token(self, *scopes, **kwargs):  # pragma: no cover - never invoked
        raise AssertionError("network token request should not happen in tests")


def _broker(ttl: int | None = None) -> AzureBlobBroker:
    if ttl is None:
        return AzureBlobBroker(account_url=ACCOUNT_URL, credential=_StubCredential())
    return AzureBlobBroker(
        account_url=ACCOUNT_URL, ttl=ttl, credential=_StubCredential()
    )


def test_parse_resource_splits_container_and_blob():
    broker = _broker()
    container, blob = broker._parse_resource("az://my-container/path/to/blob.parquet")
    assert container == "my-container"
    assert blob == "path/to/blob.parquet"


def test_parse_resource_rejects_non_az_scheme():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("gs://my-container/blob")


def test_parse_resource_rejects_missing_blob():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("az://my-container")


def test_parse_resource_rejects_empty_blob():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("az://my-container/")


def test_parse_resource_rejects_missing_container():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("az:///blob.parquet")


def test_resolve_permission_maps_known_actions():
    broker = _broker()

    read = broker._resolve_permission("read")
    assert isinstance(read, BlobSasPermissions)
    assert read.read is True

    write = broker._resolve_permission("write")
    assert write.write is True
    assert write.create is True

    delete = broker._resolve_permission("delete")
    assert delete.delete is True

    tag = broker._resolve_permission("tag")
    assert tag.tag is True


def test_resolve_permission_rejects_unknown_action():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._resolve_permission("admin")


def test_account_name_is_first_hostname_label():
    broker = _broker()
    assert broker._account_name() == "acct"


def _patch_sdk(monkeypatch, captured=None):
    """Patch the lazily-imported Azure SDK calls used by issue()."""
    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.get_user_delegation_key",
        lambda self, start, expiry: object(),
    )

    def fake_generate_blob_sas(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return "sv=2024-01-01&sig=fake-signature"

    monkeypatch.setattr(
        "azure.storage.blob.generate_blob_sas",
        fake_generate_blob_sas,
    )


def test_issue_returns_scoped_ephemeral_credential(monkeypatch):
    _patch_sdk(monkeypatch)
    broker = _broker()
    cred = broker.issue("txn-123", "az://my-container/object.parquet", "read")

    assert isinstance(cred, EphemeralCredential)
    assert cred.token == {
        "sas_token": "sv=2024-01-01&sig=fake-signature",
        "url": (
            f"{ACCOUNT_URL}/my-container/object.parquet"
            "?sv=2024-01-01&sig=fake-signature"
        ),
    }
    assert cred.scope == "read:az://my-container/object.parquet"
    assert cred.transaction_id == "txn-123"
    assert cred.lease_id is None
    assert cred.metadata["account_url"] == ACCOUNT_URL
    assert cred.metadata["container"] == "my-container"
    assert cred.metadata["permission"] == "read"


def test_issue_sets_expiry_as_utc_unix_timestamp(monkeypatch):
    captured: dict = {}
    _patch_sdk(monkeypatch, captured)
    ttl = 900
    broker = _broker(ttl=ttl)
    cred = broker.issue("txn-1", "az://b/o", "read")

    assert abs(cred.expiry - (int(time.time()) + ttl)) <= 5
    assert captured["expiry"] - captured["start"] == timedelta(seconds=ttl)


def test_issue_defaults_to_fifteen_minute_expiry(monkeypatch):
    captured: dict = {}
    _patch_sdk(monkeypatch, captured)
    broker = _broker()  # no ttl -> default 900s
    broker.issue("txn-1", "az://b/o", "read")

    assert captured["expiry"] - captured["start"] == timedelta(seconds=900)


def test_issue_passes_permission_and_expiry_to_generate_blob_sas(monkeypatch):
    captured: dict = {}
    _patch_sdk(monkeypatch, captured)
    broker = _broker()
    broker.issue("txn-1", "az://my-container/object.parquet", "write")

    permission = captured["permission"]
    assert isinstance(permission, BlobSasPermissions)
    assert permission.write is True
    assert permission.create is True
    assert captured["container_name"] == "my-container"
    assert captured["blob_name"] == "object.parquet"
    assert captured["account_name"] == "acct"
    assert captured["expiry"] == captured["start"] + timedelta(seconds=900)


def test_issue_wraps_sdk_failure_in_broker_error(monkeypatch):
    def boom(self, start, expiry):
        raise RuntimeError("user delegation key request rejected")

    monkeypatch.setattr(
        "azure.storage.blob.BlobServiceClient.get_user_delegation_key",
        boom,
    )
    broker = _broker()
    with pytest.raises(IPTBrokerError):
        broker.issue("txn-1", "az://b/o", "read")


def test_revoke_is_a_noop(monkeypatch):
    _patch_sdk(monkeypatch)
    broker = _broker()
    cred = broker.issue("txn-1", "az://b/o", "read")
    assert broker.revoke(cred) is None


def test_blast_radius_names_single_blob(monkeypatch):
    _patch_sdk(monkeypatch)
    broker = _broker()
    cred = broker.issue("txn-1", "az://my-container/obj.parquet", "read")
    assert broker.blast_radius(cred) == (
        "Single Azure blob: read:az://my-container/obj.parquet"
    )


def test_azure_blob_broker_is_lazily_exported_from_package_root():
    import pymayfly

    assert pymayfly.AzureBlobBroker is AzureBlobBroker
    assert "AzureBlobBroker" in pymayfly.__all__
