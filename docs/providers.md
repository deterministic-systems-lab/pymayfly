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

## Azure Blob Provider

The built-in `AzureBlobBroker` issues an AAD-signed User Delegation SAS scoped to
a single blob. It obtains a user delegation key from the blob service and then
calls `generate_blob_sas(...)` to mint a SAS pinned to one container/blob, one
permission set, and a short expiry.
## GCS Provider

The built-in `GCSBroker` issues a downscoped Google Cloud Storage access token
scoped to a single object. It impersonates a service account (setting the token
TTL) and then applies a Credential Access Boundary pinned to one object and one
role.

Install it with:

```bash
pip install pymayfly[azure]
pip install pymayfly[gcp]
```

Example:

```python
from azure.storage.blob import BlobClient

from pymayfly import AzureBlobBroker, transaction_scope

broker = AzureBlobBroker(account_url="https://acct.blob.core.windows.net")

with transaction_scope(
    broker,
    resource="az://my-container/path/to/object.parquet",
    action="read",
) as creds:
    blob = BlobClient.from_blob_url(creds.token["url"])
    data = blob.download_blob().readall()
    ...
```

`creds.token["url"]` is the full blob URL with the SAS query string appended,
usable directly with any azure-storage-blob client. `creds.token["sas_token"]` is
the bare SAS query string for callers that build their own URLs.

Actions map to a `BlobSasPermissions` permission set (`read` -> read,
`write` -> write + create, `delete` -> delete, `tag` -> tag); any other value
raises `IPTScopeError`. Credentials expire 15 minutes after issuance (the default
`ttl=900`). Like AWS STS and GCS, an individual SAS cannot be revoked — revoking
the user delegation key is account-wide — so `revoke()` is a no-op and the TTL is
the backstop.
from google.oauth2.credentials import Credentials
from google.cloud import storage

from pymayfly import GCSBroker, transaction_scope

broker = GCSBroker(target_principal="ipt@my-project.iam.gserviceaccount.com")

with transaction_scope(
    broker,
    resource="gs://my-bucket/path/to/object.parquet",
    action="read",
) as creds:
    client = storage.Client(
        credentials=Credentials(token=creds.token["access_token"])
    )
    ...
```

The example uses `google-cloud-storage`, which is a separate install
(`pip install google-cloud-storage`); the `pymayfly[gcp]` extra installs only the
credential libraries (`google-auth`, `requests`). `creds.token["access_token"]`
is a plain bearer token usable with any GCS client.

Actions map to predefined storage roles (`read` -> `roles/storage.objectViewer`,
`write` -> `roles/storage.objectCreator`, `delete` -> `roles/storage.objectUser`);
any other value is treated as a literal role. `delete` maps to `objectUser`
because GCS has no delete-only predefined role — it also grants read/create on
that one object (still bounded to the single object by the access boundary).
Like AWS STS, GCS downscoped tokens cannot be explicitly revoked, so `revoke()`
is a no-op and the TTL is the backstop.

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
