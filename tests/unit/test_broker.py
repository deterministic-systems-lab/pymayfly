import time

import pytest

from pymayfly.core.broker import EphemeralCredential
from pymayfly.exceptions import IPTBrokerError


def test_credential_not_expired(broker):
    cred = broker.issue("txn-1", "s3://bucket/key", "read")
    assert not cred.is_expired
    assert cred.ttl > 0


def test_credential_ttl_within_range(broker):
    cred = broker.issue("txn-1", "s3://bucket/key", "read")
    assert 898 <= cred.ttl <= 901


def test_credential_scope_set(broker):
    cred = broker.issue("txn-1", "s3://bucket/key.parquet", "read")
    assert cred.scope == "read:s3://bucket/key.parquet"


def test_credential_transaction_id_preserved(broker):
    cred = broker.issue("my-txn-id", "s3://bucket/key", "write")
    assert cred.transaction_id == "my-txn-id"


def test_revoke_tracked(broker):
    cred = broker.issue("txn-1", "s3://bucket/key", "read")
    broker.revoke(cred)
    assert cred in broker.revoked


def test_blast_radius_descriptive(broker):
    cred = broker.issue("txn-1", "s3://bucket/key", "read")
    radius = broker.blast_radius(cred)
    assert "read:s3://bucket/key" in radius


def test_failing_broker_raises(failing_broker):
    with pytest.raises(IPTBrokerError):
        failing_broker.issue("txn-1", "s3://bucket/key", "read")


def test_expired_credential_property():
    cred = EphemeralCredential(
        token={},
        expiry=int(time.time()) - 10,
        scope="read:s3://bucket/key",
        transaction_id="txn-1",
    )
    assert cred.is_expired
    assert cred.ttl == 0


def test_credential_repr_contains_key_fields(broker):
    cred = broker.issue("txn-repr", "s3://bucket/key", "read")
    r = repr(cred)
    assert "txn-repr" in r
    assert "read:s3://bucket/key" in r
