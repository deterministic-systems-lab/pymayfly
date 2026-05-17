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

## Audit Records

Each transaction should produce an open record and then either a close or failure
record. The built-in `FileAuditLedger` is useful for local and single-process
pipelines, but production distributed systems should use durable centralized
logging.

## Boundaries

AWS STS credentials cannot be explicitly revoked. The security backstop is the
credential TTL and the narrow inline session policy. If immediate revocation is a
hard requirement, use or implement a provider backed by revocable leases.
