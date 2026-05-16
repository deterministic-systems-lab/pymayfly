"""
Shared test fixtures.

MockBroker allows all unit tests to run without any cloud provider.
It issues real EphemeralCredential objects with a synthetic token,
supports explicit revocation tracking, and raises on expired credentials.
"""

from __future__ import annotations

import time

import pytest

from pymayfly.core.broker import EphemeralCredential, IdentityBroker


class MockBroker(IdentityBroker):
    """
    In-memory broker for testing. No cloud dependencies.

    Tracks issued and revoked credentials so tests can assert
    on broker behavior without hitting real APIs.
    """

    def __init__(self, ttl: int = 900, fail_on_issue: bool = False):
        self.ttl = ttl
        self.fail_on_issue = fail_on_issue
        self.issued: list[EphemeralCredential] = []
        self.revoked: list[EphemeralCredential] = []

    def issue(self, transaction_id: str, resource: str, action: str) -> EphemeralCredential:
        from pymayfly.exceptions import IPTBrokerError
        if self.fail_on_issue:
            raise IPTBrokerError("MockBroker configured to fail on issue")

        cred = EphemeralCredential(
            token={"mock_key": f"mock-token-{transaction_id[:8]}"},
            expiry=int(time.time()) + self.ttl,
            scope=f"{action}:{resource}",
            transaction_id=transaction_id,
            lease_id=f"mock-lease-{transaction_id[:8]}",
        )
        self.issued.append(cred)
        return cred

    def revoke(self, credential: EphemeralCredential) -> None:
        self.revoked.append(credential)

    def blast_radius(self, credential: EphemeralCredential) -> str:
        return f"Mock resource: {credential.scope}"


class ExpiredMockBroker(MockBroker):
    """Issues credentials that are already expired. For error path testing."""

    def issue(self, transaction_id: str, resource: str, action: str) -> EphemeralCredential:
        cred = super().issue(transaction_id, resource, action)
        cred.expiry = int(time.time()) - 1  # already expired
        return cred


@pytest.fixture
def broker() -> MockBroker:
    return MockBroker()


@pytest.fixture
def expired_broker() -> ExpiredMockBroker:
    return ExpiredMockBroker()


@pytest.fixture
def failing_broker() -> MockBroker:
    return MockBroker(fail_on_issue=True)
