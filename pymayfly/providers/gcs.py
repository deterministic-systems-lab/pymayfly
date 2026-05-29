"""
GCS identity broker for the IPT protocol.

Requires: pip install pymayfly[gcp]

Issues short-lived credentials scoped to a single GCS object via
service-account impersonation plus a Credential Access Boundary (CAB).
The impersonation step sets the token lifetime (TTL); the CAB narrows
the token to exactly one object and one role.

Security guarantee:
    A compromised credential grants the requested role on exactly one
    GCS object. If the source object is deleted after processing, the
    credential points at a nonexistent resource for the remainder of
    its TTL.

Revocation:
    GCP does not support explicit revocation of these downscoped tokens.
    The TTL is the security backstop, mirroring AWS STS.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC
from typing import Any

from ..core.broker import EphemeralCredential, IdentityBroker
from ..exceptions import IPTBrokerError, IPTScopeError

logger = logging.getLogger(__name__)

# Action map: simple strings -> predefined GCS storage roles.
# Unknown actions are passed through as literal role strings.
_ACTION_MAP: dict[str, str] = {
    "read": "roles/storage.objectViewer",
    "write": "roles/storage.objectCreator",  # create / overwrite
    # No delete-only predefined role exists; objectUser also grants read/create,
    # but the access boundary still pins it to the single requested object.
    "delete": "roles/storage.objectUser",
}


class GCSBroker(IdentityBroker):
    """
    Issues downscoped GCS credentials scoped to a single object.

    Args:
        target_principal:   Service account email to impersonate.
        ttl:                Impersonated-token lifetime in seconds. Default 900.
        source_credentials: Source credentials for impersonation. Defaults to
                            Application Default Credentials, resolved lazily so
                            import never fails without GCP configuration.
        target_scopes:      OAuth scopes for the impersonated token. The CAB
                            narrows access below these. Default cloud-platform.
    """

    def __init__(
        self,
        target_principal: str,
        ttl: int = 900,
        source_credentials: Any = None,
        target_scopes: tuple[str, ...] = (
            "https://www.googleapis.com/auth/cloud-platform",
        ),
    ) -> None:
        self._target_principal = target_principal
        self._ttl = ttl
        self._source_credentials = source_credentials
        self._target_scopes = list(target_scopes)

    def _parse_resource(self, resource: str) -> tuple[str, str]:
        if not resource.startswith("gs://"):
            raise IPTScopeError(
                f"GCS resource must be a gs:// URI. Got: {resource!r}"
            )
        without_scheme = resource[len("gs://"):]
        bucket, sep, obj = without_scheme.partition("/")
        if not bucket or not sep or not obj:
            raise IPTScopeError(
                "GCS resource must include bucket and object "
                f"(gs://bucket/object). Got: {resource!r}"
            )
        if any(ch in obj for ch in ("'", "\\", "\n", "\r")):
            raise IPTScopeError(
                "GCS object name contains characters that cannot be safely "
                "embedded in an access-boundary condition (single quote, "
                f"backslash, or newline). Got: {resource!r}"
            )
        return bucket, obj

    def _resolve_role(self, action: str) -> str:
        return _ACTION_MAP.get(action, action)

    def _build_boundary(self, bucket: str, obj: str, role: str) -> Any:
        from google.auth import downscoped

        rule = downscoped.AccessBoundaryRule(
            available_resource=(
                f"//storage.googleapis.com/projects/_/buckets/{bucket}"
            ),
            available_permissions=[f"inRole:{role}"],
            availability_condition=downscoped.AvailabilityCondition(
                expression=(
                    f"resource.name == 'projects/_/buckets/{bucket}/objects/{obj}'"
                ),
            ),
        )
        return downscoped.CredentialAccessBoundary(rules=[rule])

    def _get_source_credentials(self) -> Any:
        if self._source_credentials is None:
            try:
                import google.auth
            except ImportError as exc:
                raise IPTBrokerError(
                    "google-auth is required for GCSBroker. "
                    "Install it with: pip install pymayfly[gcp]"
                ) from exc
            self._source_credentials, _ = google.auth.default(
                scopes=self._target_scopes
            )
        return self._source_credentials

    def issue(
        self,
        transaction_id: str,
        resource: str,
        action: str,
    ) -> EphemeralCredential:
        bucket, obj = self._parse_resource(resource)
        role = self._resolve_role(action)
        source = self._get_source_credentials()

        try:
            from google.auth import downscoped, impersonated_credentials
            from google.auth.transport.requests import Request
        except ImportError as exc:
            raise IPTBrokerError(
                "google-auth is required for GCSBroker. "
                "Install it with: pip install pymayfly[gcp]"
            ) from exc

        try:
            impersonated = impersonated_credentials.Credentials(
                source_credentials=source,
                target_principal=self._target_principal,
                target_scopes=self._target_scopes,
                lifetime=self._ttl,
            )
            creds = downscoped.Credentials(
                source_credentials=impersonated,
                credential_access_boundary=self._build_boundary(bucket, obj, role),
            )
            creds.refresh(Request())
        except Exception as exc:
            raise IPTBrokerError(
                f"GCS credential issuance failed for transaction {transaction_id}: {exc}"
            ) from exc

        if creds.expiry is not None:
            expiry_dt = creds.expiry
            if expiry_dt.tzinfo is None:
                # google-auth historically returned naive UTC datetimes
                expiry_dt = expiry_dt.replace(tzinfo=UTC)
            expiry = int(expiry_dt.timestamp())
        else:
            expiry = int(time.time()) + self._ttl

        logger.info(
            "IPT credential issued",
            extra={
                "transaction_id": transaction_id,
                "resource": resource,
                "action": action,
                "target_principal": self._target_principal,
                "role": role,
            },
        )

        return EphemeralCredential(
            token={"access_token": creds.token, "token_type": "Bearer"},
            expiry=expiry,
            scope=f"{action}:{resource}",
            transaction_id=transaction_id,
            lease_id=None,  # GCS does not support revocation
            metadata={
                "target_principal": self._target_principal,
                "role": role,
            },
        )

    def revoke(self, credential: EphemeralCredential) -> None:
        """
        No-op. GCP does not support explicit revocation of downscoped
        tokens. The TTL is the security backstop. If the source object
        is deleted after processing, the credential points at a
        nonexistent resource for the remainder of its TTL.
        """
        logger.debug(
            "GCSBroker.revoke() called — GCS downscoped tokens cannot be "
            "explicitly revoked. TTL backstop: %ds. transaction_id=%s",
            credential.ttl,
            credential.transaction_id,
        )

    def blast_radius(self, credential: EphemeralCredential) -> str:
        return f"Single GCS object: {credential.scope}"
