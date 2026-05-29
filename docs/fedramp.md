# FedRAMP Deployment Notes

pymayfly is a library component. FedRAMP suitability depends on the surrounding
system, IAM configuration, logging controls, and operational process. The notes
below are implementation guidance, not an authorization claim.

## AWS STS

`AWSSTSBroker` assumes an IAM role and attaches an inline session policy scoped
to a single S3 object ARN.

Recommended controls:

- Use a dedicated role for IPT processing.
- Scope the role trust policy to the workload identity that issues transactions.
- Keep the STS duration at the minimum supported value unless the transaction
  genuinely needs longer.
- Delete or quarantine source objects after processing when that is part of the
  pipeline design.
- Send audit records to durable, access-controlled storage.
- Monitor AssumeRole events in CloudTrail.

## Azure Blob

`AzureBlobBroker` issues an AAD-signed User Delegation SAS scoped to a single
blob.

Recommended controls:

- Use a dedicated AAD identity or managed identity for IPT processing.
- Grant it only the Storage Blob Data role needed on the target container.
- Keep the SAS `ttl` at the 15-minute default unless a longer lifetime is
  genuinely required.
- Delete or quarantine source blobs after processing when that is part of the
  pipeline design.
- Send audit records to durable, access-controlled storage.
- Monitor user-delegation-key usage and SAS issuance in Azure Monitor and
  storage logs.

## GCS

`GCSBroker` issues a downscoped access token via service-account impersonation
plus a Credential Access Boundary pinned to a single object.

Recommended controls:

- Use a dedicated impersonation target service account for IPT processing.
- Grant it only the least-privilege roles needed on the target object.
- Keep the impersonation lifetime at the minimum needed unless the transaction
  genuinely needs longer.
- Delete or quarantine source objects after processing when that is part of the
  pipeline design.
- Send audit records to durable, access-controlled storage.
- Monitor impersonation and token issuance in Cloud Audit Logs.

## Audit Records

Each transaction should produce an open record and then either a close or failure
record. The built-in `FileAuditLedger` is useful for local and single-process
pipelines, but production distributed systems should use durable centralized
logging.

## Boundaries

None of the shipped providers issue individually revocable credentials. AWS STS
credentials cannot be explicitly revoked. An individual Azure User Delegation SAS
cannot be revoked either; revoking the user delegation key is an account-wide
action. GCS downscoped tokens likewise cannot be revoked. For all three, the
security backstop is the credential TTL and the narrow scope of the issued
credential. If immediate revocation is a hard requirement, use or implement a
provider backed by revocable leases.
