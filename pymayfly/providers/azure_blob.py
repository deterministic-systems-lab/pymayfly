"""
Azure Blob identity broker for the IPT protocol.

Requires: pip install pymayfly[azure]

Issues a short-lived, AAD-signed User Delegation SAS scoped to a single
blob via generate_blob_sas(). The user delegation key is obtained from a
BlobServiceClient authenticated with an azure-identity credential; the
SAS is pinned to exactly one container/blob, one permission set, and a
short expiry — not the container, not a prefix, not a wildcard.

Security guarantee:
    A compromised credential grants the requested permission on exactly
    one blob. If the source blob is deleted after processing, the
    credential points at a nonexistent resource for the remainder of its
    TTL.

Revocation:
    Azure does not support revoking an individual SAS — revoking the
    user delegation key is account-wide. The 15-minute TTL is the
    security backstop, mirroring AWS STS and GCS.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ..core.broker import EphemeralCredential, IdentityBroker
from ..exceptions import IPTBrokerError, IPTScopeError

logger = logging.getLogger(__name__)


class AzureBlobBroker(IdentityBroker):
    """
    Issues a User Delegation SAS scoped to a single Azure blob.

    Args:
        account_url: Blob service endpoint, e.g.
                     "https://acct.blob.core.windows.net".
        ttl:         SAS lifetime in seconds. Default 900 (15 minutes);
                     every issued SAS expires ttl seconds after issuance.
        credential:  azure-identity credential used to obtain the user
                     delegation key. Defaults to a lazily-resolved
                     DefaultAzureCredential so import never fails without
                     azure installed; injectable for tests.

    Example::

        broker = AzureBlobBroker(
            account_url="https://acct.blob.core.windows.net",
            ttl=900,
        )

        with transaction_scope(
            broker,
            resource="az://my-container/file.parquet",
            action="read",
        ) as creds:
            blob = BlobClient.from_blob_url(creds.token["url"])
    """

    def __init__(
        self,
        account_url: str,
        ttl: int = 900,
        credential: Any = None,
    ) -> None:
        self._account_url = account_url
        self._ttl = ttl
        self._credential = credential

    def _parse_resource(self, resource: str) -> tuple[str, str]:
        if not resource.startswith("az://"):
            raise IPTScopeError(
                f"Azure resource must be an az:// URI. Got: {resource!r}"
            )
        without_scheme = resource[len("az://"):]
        container, sep, blob = without_scheme.partition("/")
        if not container or not sep or not blob:
            raise IPTScopeError(
                "Azure resource must include container and blob "
                f"(az://container/blob). Got: {resource!r}"
            )
        return container, blob

    def _resolve_permission(self, action: str) -> Any:
        from azure.storage.blob import BlobSasPermissions

        if action == "read":
            return BlobSasPermissions(read=True)
        if action == "write":
            return BlobSasPermissions(write=True, create=True)
        if action == "delete":
            return BlobSasPermissions(delete=True)
        if action == "tag":
            return BlobSasPermissions(tag=True)
        raise IPTScopeError(
            f"Unknown action for AzureBlobBroker: {action!r}. "
            "Expected one of: read, write, delete, tag."
        )

    def _account_name(self) -> str:
        without_scheme = self._account_url.split("://", 1)[-1]
        host = without_scheme.split("/", 1)[0]
        return host.split(".", 1)[0]

    def _get_credential(self) -> Any:
        if self._credential is None:
            try:
                from azure.identity import DefaultAzureCredential
            except ImportError as exc:
                raise IPTBrokerError(
                    "azure-identity is required for AzureBlobBroker. "
                    "Install it with: pip install pymayfly[azure]"
                ) from exc
            self._credential = DefaultAzureCredential()
        return self._credential

    def issue(
        self,
        transaction_id: str,
        resource: str,
        action: str,
    ) -> EphemeralCredential:
        """
        Issue a User Delegation SAS scoped to a single Azure blob.

        Args:
            transaction_id: UUID for this transaction.
            resource:       Blob URI in the form az://container/blob.
            action:         "read", "write", "delete", or "tag".
        """
        container, blob = self._parse_resource(resource)
        perm = self._resolve_permission(action)

        key_start = datetime.now(UTC)
        key_expiry = key_start + timedelta(seconds=self._ttl)

        try:
            from azure.storage.blob import (
                BlobServiceClient,
                generate_blob_sas,
            )
        except ImportError as exc:
            raise IPTBrokerError(
                "azure-storage-blob is required for AzureBlobBroker. "
                "Install it with: pip install pymayfly[azure]"
            ) from exc

        try:
            service = BlobServiceClient(
                account_url=self._account_url,
                credential=self._get_credential(),
            )
            udk = service.get_user_delegation_key(key_start, key_expiry)
            sas = generate_blob_sas(
                account_name=self._account_name(),
                container_name=container,
                blob_name=blob,
                user_delegation_key=udk,
                permission=perm,
                expiry=key_expiry,
                start=key_start,
            )
        except Exception as exc:
            raise IPTBrokerError(
                f"Azure SAS issuance failed for transaction {transaction_id}: {exc}"
            ) from exc

        expiry = int(key_expiry.timestamp())

        logger.info(
            "IPT credential issued",
            extra={
                "transaction_id": transaction_id,
                "resource": resource,
                "action": action,
                "account_url": self._account_url,
                "container": container,
                "expires": key_expiry.isoformat(),
            },
        )

        return EphemeralCredential(
            token={
                "sas_token": sas,
                "url": f"{self._account_url}/{container}/{blob}?{sas}",
            },
            expiry=expiry,
            scope=f"{action}:{resource}",
            transaction_id=transaction_id,
            lease_id=None,  # Azure does not support per-token revocation
            metadata={
                "account_url": self._account_url,
                "container": container,
                "permission": action,
            },
        )

    def revoke(self, credential: EphemeralCredential) -> None:
        """
        No-op. Azure does not support revoking an individual SAS —
        revoking the user delegation key is account-wide. The 15-minute
        TTL is the security backstop. If the source blob is deleted after
        processing, the credential points at a nonexistent resource for
        the remainder of its TTL.
        """
        logger.debug(
            "AzureBlobBroker.revoke() called — an individual SAS cannot be "
            "explicitly revoked. TTL backstop: %ds. transaction_id=%s",
            credential.ttl,
            credential.transaction_id,
        )

    def blast_radius(self, credential: EphemeralCredential) -> str:
        return f"Single Azure blob: {credential.scope}"
