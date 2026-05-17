# Provider Guide

Providers issue credentials for one transaction and describe exactly what those
credentials can touch. The core package defines the contract; provider packages
or modules adapt that contract to a platform such as AWS STS, Vault, or another
credential service.

## The IdentityBroker Contract

Every provider implements `IdentityBroker`:

```python
from pymayfly import EphemeralCredential, IdentityBroker


class MyBroker(IdentityBroker):
    def issue(self, transaction_id: str, resource: str, action: str) -> EphemeralCredential:
        ...

    def revoke(self, credential: EphemeralCredential) -> None:
        ...

    def blast_radius(self, credential: EphemeralCredential) -> str:
        ...
```

`issue()` receives a unique transaction ID, a resource identifier, and an action.
It should return an `EphemeralCredential` whose scope is no broader than that
resource/action pair.

`revoke()` is always called when `transaction_scope` exits. Providers that cannot
explicitly revoke credentials, such as AWS STS, should make this a documented
no-op and rely on short TTLs.

`blast_radius()` returns a concise audit description. Prefer specific language
such as `Single S3 object: arn:aws:s3:::bucket/key` over generic descriptions.

## AWS STS Provider

The built-in `AWSSTSBroker` creates an STS session with an inline policy scoped
to a single S3 object ARN.

Install it with:

```bash
pip install pymayfly[aws]
```

Example:

```python
from pymayfly import AWSSTSBroker, transaction_scope

broker = AWSSTSBroker(role_arn="arn:aws:iam::123456789012:role/IPTProcessor")

with transaction_scope(
    broker,
    resource="arn:aws:s3:::my-bucket/path/to/object.parquet",
    action="read",
) as creds:
    ...
```

## Provider Checklist

- Scope credentials to one resource and one action.
- Set the shortest practical expiry for the platform.
- Preserve `transaction_id` in provider metadata where possible.
- Make revocation idempotent.
- Raise `IPTBrokerError` when issuance fails.
- Avoid importing heavy provider SDKs until the provider is actually used.
- Keep provider SDK dependencies behind optional extras.

## Planned Providers

Vault and Supabase providers are planned for future releases. Until those ship,
use the `IdentityBroker` interface to integrate custom credential issuers.
