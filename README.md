# pymayfly

**Identity-Per-Transaction for regulated data pipelines.**

*Like a mayfly, these credentials live for exactly one transaction.*

[![PyPI](https://img.shields.io/pypi/v/pymayfly)](https://pypi.org/project/pymayfly/)
[![Python](https://img.shields.io/pypi/pyversions/pymayfly)](https://pypi.org/project/pymayfly/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

---

## The Problem

Most enterprise "zero trust" implementations authenticate once and trust indefinitely. A single compromised credential — a leaked IAM role, a stolen service account key, a reused session token — exposes your entire data lake for hours or days.

## The Solution

**Identity-Per-Transaction (IPT)** issues credentials scoped to exactly one resource for exactly one transaction. A compromised credential exposes one object. When that object is deleted post-processing, the credential points at nothing for the remainder of its TTL.

```
Traditional model:   compromised key → entire data lake
IPT model:           compromised key → single S3 object key (now deleted)
```

## Install

```bash
pip install pymayfly[aws]     # AWS STS backend (FedRAMP-suitable)
pip install pymayfly[gcp]     # GCS backend (impersonation + downscoped tokens)
pip install pymayfly          # core only — bring your own provider
```

## Quickstart

### Decorator (AWS Lambda)

```python
import boto3

from pymayfly import IPTEnforcer, AWSSTSBroker, FileAuditLedger

enforcer = IPTEnforcer(
    broker=AWSSTSBroker(role_arn="arn:aws:iam::123456789012:role/IPTProcessor"),
    ledger=FileAuditLedger("/var/log/mayfly/audit.jsonl"),
)

@enforcer.protect(
    resource_from=lambda e: (
        f"arn:aws:s3:::{e['Records'][0]['s3']['bucket']['name']}"
        f"/{e['Records'][0]['s3']['object']['key']}"
    ),
    action="read",
)
def handler(event, context, *, creds):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=creds.token["AccessKeyId"],
        aws_secret_access_key=creds.token["SecretAccessKey"],
        aws_session_token=creds.token["SessionToken"],
    )
    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = record["s3"]["object"]["key"]

    data = s3.get_object(Bucket=bucket, Key=key)
    # process, de-identify, write to clean zone
    # delete source object → credential now points at nothing
```

### Context Manager

```python
from pymayfly import transaction_scope, AWSSTSBroker

broker = AWSSTSBroker(role_arn="arn:aws:iam::123456789012:role/IPTProcessor")

with transaction_scope(
    broker,
    resource="arn:aws:s3:::bucket/patient-001.parquet",
    action="read",
) as creds:
    # creds scoped to exactly this object
    process(creds)
# creds revoked (or expired) here
```

## Providers

| Provider | Install | Platform | Revocation | Regulated Use |
|---|---|---|---|---|
| `AWSSTSBroker` | `pymayfly[aws]` | AWS | TTL only (900s min) | FedRAMP / HIPAA |
| `GCSBroker` | `pymayfly[gcp]` | GCP / GCS | TTL only | FedRAMP / HIPAA |
| `VaultBroker` | Planned for 0.2.0 | Any | Explicit | Any |
| `SupabaseJWTBroker` | Planned for 0.2.0 | Postgres | Blocklist | Dev / test only |

## Security Properties

| Metric | Traditional (bucket-wide role) | IPT |
|---|---|---|
| Blast radius | Entire data lake | Single object |
| Credential lifetime | Days / weeks | 900s |
| Post-deletion access | Credential still valid | Credential points at nothing |
| Audit granularity | Session-level | Transaction-level |

For a 1M-object data lake: blast radius reduced by **99.999%**.

## Implementing a Custom Provider

Subclass `IdentityBroker` and implement three methods:

```python
from pymayfly import IdentityBroker, EphemeralCredential

class MyBroker(IdentityBroker):
    def issue(self, transaction_id, resource, action) -> EphemeralCredential:
        ...
    def revoke(self, credential) -> None:
        ...
    def blast_radius(self, credential) -> str:
        ...
```

See [docs/providers.md](docs/providers.md) for a provider walkthrough and
`pymayfly/providers/aws_sts.py` for a complete implementation.

## Research

This library implements the Identity-Per-Transaction protocol described in:

> McKinnon, T. (2026). *Zero-Trust Data Engineering: A Reference Architecture
> for Serverless, FedRAMP-High Healthcare Pipelines.*
> IEEE BigDataSecurity 2026.
> [TechRxiv preprint](https://doi.org/10.36227/techrxiv.174375803.76224567/v1)

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Provider contributions especially encouraged — if you implement a Vault, Azure,
or GCP backend, open a PR. Use the [new provider issue template](.github/ISSUE_TEMPLATE/new_provider.md).

## License

Apache 2.0. See [LICENSE](LICENSE).

---

*Built and maintained by [Deterministic Systems Lab](https://deterministicsystemslab.io).*
