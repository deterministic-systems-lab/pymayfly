# Security Policy

## Supported Versions

pymayfly is currently pre-1.0. Security fixes are released on the latest minor
version.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Reporting A Vulnerability

Please do not open a public issue for a suspected vulnerability.

Report security concerns by email:

```text
tristan@deterministicsystemslab.io
```

Include:

- A concise description of the issue.
- Steps to reproduce, if available.
- Affected versions or commits.
- Any relevant logs, stack traces, or proof-of-concept details.

You should receive an initial response within 72 hours. If the issue is
confirmed, the fix and disclosure timeline will be coordinated before public
release.

## Scope

In scope:

- Credential scope expansion.
- Credential reuse across transactions.
- Failure paths that skip revocation when revocation is supported.
- Audit records that misrepresent transaction state.
- Packaging issues that install unintended dependencies.

Out of scope:

- Misconfigured cloud IAM policies outside this repository.
- Vulnerabilities in optional provider SDKs such as `boto3`.
- Findings that require already-compromised maintainer credentials.
