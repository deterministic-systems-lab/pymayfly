from datetime import UTC, datetime

import pytest
from google.auth import downscoped, impersonated_credentials
from google.auth.credentials import AnonymousCredentials

from pymayfly.core.broker import EphemeralCredential
from pymayfly.exceptions import IPTBrokerError, IPTScopeError
from pymayfly.providers.gcs import GCSBroker


def _broker() -> GCSBroker:
    return GCSBroker(target_principal="ipt@my-project.iam.gserviceaccount.com")


def test_parse_resource_splits_bucket_and_object():
    broker = _broker()
    bucket, obj = broker._parse_resource("gs://my-bucket/path/to/object.parquet")
    assert bucket == "my-bucket"
    assert obj == "path/to/object.parquet"


def test_parse_resource_rejects_non_gs_scheme():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("arn:aws:s3:::my-bucket/key")


def test_parse_resource_rejects_missing_object():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("gs://my-bucket")


def test_parse_resource_rejects_empty_object():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("gs://my-bucket/")


def test_resolve_role_maps_known_actions():
    broker = _broker()
    assert broker._resolve_role("read") == "roles/storage.objectViewer"
    assert broker._resolve_role("write") == "roles/storage.objectCreator"
    assert broker._resolve_role("delete") == "roles/storage.objectUser"


def test_resolve_role_passes_through_literal_role():
    broker = _broker()
    assert broker._resolve_role("roles/storage.objectAdmin") == "roles/storage.objectAdmin"


def test_build_boundary_pins_single_object_and_role():
    broker = _broker()
    boundary = broker._build_boundary(
        bucket="my-bucket",
        obj="path/to/object.parquet",
        role="roles/storage.objectViewer",
    )
    rules = boundary.rules
    assert len(rules) == 1
    rule = rules[0]
    assert rule.available_resource == (
        "//storage.googleapis.com/projects/_/buckets/my-bucket"
    )
    assert rule.available_permissions == ("inRole:roles/storage.objectViewer",)
    assert rule.availability_condition.expression == (
        "resource.name == "
        "'projects/_/buckets/my-bucket/objects/path/to/object.parquet'"
    )


def _patch_refresh(monkeypatch, token="downscoped-token-xyz", expiry=datetime(2030, 1, 1)):
    def fake_refresh(self, request):
        self.token = token
        self.expiry = expiry
    monkeypatch.setattr(downscoped.Credentials, "refresh", fake_refresh)


def test_issue_returns_scoped_ephemeral_credential(monkeypatch):
    _patch_refresh(monkeypatch)
    broker = GCSBroker(
        target_principal="ipt@my-project.iam.gserviceaccount.com",
        source_credentials=AnonymousCredentials(),
    )
    cred = broker.issue("txn-123", "gs://my-bucket/object.parquet", "read")

    assert isinstance(cred, EphemeralCredential)
    assert cred.token == {"access_token": "downscoped-token-xyz", "token_type": "Bearer"}
    assert cred.scope == "read:gs://my-bucket/object.parquet"
    assert cred.transaction_id == "txn-123"
    assert cred.lease_id is None
    assert cred.metadata["target_principal"] == "ipt@my-project.iam.gserviceaccount.com"
    assert cred.metadata["role"] == "roles/storage.objectViewer"


def test_issue_sets_expiry_as_utc_unix_timestamp(monkeypatch):
    expiry = datetime(2030, 1, 1, 0, 0, 0)
    _patch_refresh(monkeypatch, expiry=expiry)
    broker = GCSBroker(
        target_principal="ipt@my-project.iam.gserviceaccount.com",
        source_credentials=AnonymousCredentials(),
    )
    cred = broker.issue("txn-1", "gs://b/o", "read")
    assert cred.expiry == int(expiry.replace(tzinfo=UTC).timestamp())


def test_issue_passes_ttl_as_impersonation_lifetime(monkeypatch):
    _patch_refresh(monkeypatch)
    captured: dict = {}
    real_init = impersonated_credentials.Credentials.__init__

    def spy_init(self, *args, **kwargs):
        captured.update(kwargs)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(impersonated_credentials.Credentials, "__init__", spy_init)
    broker = GCSBroker(
        target_principal="ipt@my-project.iam.gserviceaccount.com",
        ttl=600,
        source_credentials=AnonymousCredentials(),
    )
    broker.issue("txn-1", "gs://b/o", "read")
    assert captured["lifetime"] == 600
    assert captured["target_principal"] == "ipt@my-project.iam.gserviceaccount.com"


def test_issue_wraps_refresh_failure_in_broker_error(monkeypatch):
    def boom(self, request):
        raise RuntimeError("token exchange rejected")
    monkeypatch.setattr(downscoped.Credentials, "refresh", boom)
    broker = GCSBroker(
        target_principal="ipt@my-project.iam.gserviceaccount.com",
        source_credentials=AnonymousCredentials(),
    )
    with pytest.raises(IPTBrokerError):
        broker.issue("txn-1", "gs://b/o", "read")


def test_revoke_is_a_noop(monkeypatch):
    _patch_refresh(monkeypatch)
    broker = GCSBroker(
        target_principal="ipt@my-project.iam.gserviceaccount.com",
        source_credentials=AnonymousCredentials(),
    )
    cred = broker.issue("txn-1", "gs://b/o", "read")
    assert broker.revoke(cred) is None


def test_blast_radius_names_single_object(monkeypatch):
    _patch_refresh(monkeypatch)
    broker = GCSBroker(
        target_principal="ipt@my-project.iam.gserviceaccount.com",
        source_credentials=AnonymousCredentials(),
    )
    cred = broker.issue("txn-1", "gs://my-bucket/object.parquet", "read")
    assert broker.blast_radius(cred) == (
        "Single GCS object: read:gs://my-bucket/object.parquet"
    )


def test_issue_handles_tz_aware_expiry(monkeypatch):
    expiry = datetime(2030, 1, 1, 0, 0, 0, tzinfo=UTC)
    _patch_refresh(monkeypatch, expiry=expiry)
    broker = GCSBroker(
        target_principal="ipt@my-project.iam.gserviceaccount.com",
        source_credentials=AnonymousCredentials(),
    )
    cred = broker.issue("txn-1", "gs://b/o", "read")
    assert cred.expiry == int(expiry.timestamp())


def test_gcs_broker_is_lazily_exported_from_package_root():
    import pymayfly

    assert pymayfly.GCSBroker is GCSBroker
    assert "GCSBroker" in pymayfly.__all__


def test_parse_resource_rejects_single_quote_in_object_name():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("gs://my-bucket/evil' || resource.name.startsWith('x")


def test_parse_resource_rejects_backslash_in_object_name():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("gs://my-bucket/evil\\name.parquet")


def test_parse_resource_rejects_newline_in_object_name():
    broker = _broker()
    with pytest.raises(IPTScopeError):
        broker._parse_resource("gs://my-bucket/evil\nname.parquet")
