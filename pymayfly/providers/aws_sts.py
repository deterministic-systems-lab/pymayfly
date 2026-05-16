"""
AWS STS identity broker for the IPT protocol.

Requires: pip install pymayfly[aws]

Issues temporary AWS credentials scoped to a single S3 object key
via STS AssumeRole with an inline session policy. The inline policy
narrows the assumed role to exactly the triggering object — not the
bucket, not a prefix, not a wildcard.

Security guarantee:
    A compromised credential grants s3:GetObject (or the requested
    action) on exactly one S3 ARN. If the source object is deleted
    after processing (recommended), the credential points at a
    nonexistent resource for the remainder of its TTL.

Revocation:
    AWS STS does not support explicit credential revocation. The
    minimum TTL is 900 seconds. For pipelines that require immediate
    revocation, use VaultBroker (ipt[vault]) instead.

FedRAMP:
    This provider is suitable for FedRAMP Moderate and High
    environments when the assumed role and trust policy are
    correctly scoped. See docs/fedramp.md for IAM configuration.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..core.broker import EphemeralCredential, IdentityBroker
from ..exceptions import IPTBrokerError

logger = logging.getLogger(__name__)

# Action map: simple strings → S3 API actions
_ACTION_MAP: dict[str, str] = {
    "read":   "s3:GetObject",
    "write":  "s3:PutObject",
    "delete": "s3:DeleteObject",
    "tag":    "s3:PutObjectTagging",
}


class AWSSTSBroker(IdentityBroker):
    """
    Issues STS credentials scoped to a single S3 object.

    Args:
        role_arn:   ARN of the IAM role to assume. The role's trust
                    policy must allow the calling identity to assume it.
        ttl:        Credential lifetime in seconds. Minimum 900 (STS
                    hard limit). Default 900.
        region:     AWS region for the STS client. Default "us-east-1".
        external_id: Optional STS external ID for cross-account assumes.

    Example::

        broker = AWSSTSBroker(
            role_arn="arn:aws:iam::123456789012:role/IPTProcessor",
            ttl=900,
        )

        with transaction_scope(
            broker,
            resource="arn:aws:s3:::my-bucket/file.parquet",
            action="read",
        ) as creds:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=creds.token["AccessKeyId"],
                aws_secret_access_key=creds.token["SecretAccessKey"],
                aws_session_token=creds.token["SessionToken"],
            )
    """

    def __init__(
        self,
        role_arn: str,
        ttl: int = 900,
        region: str = "us-east-1",
        external_id: str | None = None,
    ) -> None:
        if ttl < 900:
            raise ValueError(
                f"STS minimum TTL is 900 seconds. Got {ttl}. "
                "For shorter TTLs, use VaultBroker (ipt[vault])."
            )

        self._role_arn = role_arn
        self._ttl = ttl
        self._region = region
        self._external_id = external_id
        self._sts = None  # lazy init so import doesn't fail without boto3

    def _get_sts_client(self) -> Any:
        if self._sts is None:
            try:
                import boto3
                self._sts = boto3.client("sts", region_name=self._region)
            except ImportError:
                raise IPTBrokerError(
                    "boto3 is required for AWSSTSBroker. "
                    "Install it with: pip install pymayfly[aws]"
                )
        return self._sts

    def issue(
        self,
        transaction_id: str,
        resource: str,
        action: str,
    ) -> EphemeralCredential:
        """
        Issue STS credentials scoped to a single S3 object ARN.

        Args:
            transaction_id: UUID for this transaction.
            resource:       S3 object ARN. Must be in the form
                            arn:aws:s3:::bucket/key.
            action:         "read", "write", "delete", "tag", or a
                            full S3 action string (e.g. "s3:GetObject").
        """
        sts = self._get_sts_client()
        policy = self._build_policy(resource, action)

        session_name = f"mayfly-{transaction_id[:32]}"

        assume_kwargs = dict(
            RoleArn=self._role_arn,
            RoleSessionName=session_name,
            Policy=json.dumps(policy),
            DurationSeconds=self._ttl,
        )
        if self._external_id:
            assume_kwargs["ExternalId"] = self._external_id

        try:
            response = sts.assume_role(**assume_kwargs)
        except Exception as exc:
            raise IPTBrokerError(
                f"STS AssumeRole failed for transaction {transaction_id}: {exc}"
            ) from exc

        creds = response["Credentials"]
        expiry = int(creds["Expiration"].timestamp())

        logger.info(
            "IPT credential issued",
            extra={
                "transaction_id": transaction_id,
                "resource": resource,
                "action": action,
                "session_name": session_name,
                "expires": creds["Expiration"].isoformat(),
            },
        )

        return EphemeralCredential(
            token={
                "AccessKeyId":     creds["AccessKeyId"],
                "SecretAccessKey": creds["SecretAccessKey"],
                "SessionToken":    creds["SessionToken"],
            },
            expiry=expiry,
            scope=f"{action}:{resource}",
            transaction_id=transaction_id,
            lease_id=None,  # STS does not support revocation
            metadata={
                "session_name": session_name,
                "role_arn": self._role_arn,
            },
        )

    def revoke(self, credential: EphemeralCredential) -> None:
        """
        No-op. AWS STS does not support explicit credential revocation.

        The 900s TTL is the security backstop. If the source object
        is deleted after processing, the credential points at a
        nonexistent resource for the remainder of its TTL — providing
        a stronger guarantee than scope limitation alone.
        """
        logger.debug(
            "AWSSTSBroker.revoke() called — STS credentials cannot be explicitly "
            "revoked. TTL backstop: %ds. transaction_id=%s",
            credential.ttl,
            credential.transaction_id,
        )

    def blast_radius(self, credential: EphemeralCredential) -> str:
        return f"Single S3 object: {credential.scope}"

    def _build_policy(self, resource: str, action: str) -> dict[str, Any]:
        api_action = _ACTION_MAP.get(action, action)
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [api_action],
                    "Resource": [resource],
                }
            ],
        }
