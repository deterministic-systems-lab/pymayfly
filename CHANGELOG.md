# Changelog

All notable changes to pymayfly are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] - 2026-05-15

### Added
- `IdentityBroker` abstract base class
- `EphemeralCredential` dataclass with `is_expired`, `ttl` properties
- `transaction_scope` context manager
- `ipt_handler` decorator
- `IPTEnforcer` stateful enforcer class
- `ProvenanceRecord` with SHA-256 tamper-evident hashing
- `AuditLedger` ABC
- `ConsoleAuditLedger` — stdout JSONL, zero deps
- `FileAuditLedger` — append-only JSONL file, zero deps
- `AWSSTSBroker` — STS-backed provider (`ipt[aws]`)
- Full exception hierarchy (`IPTError`, `IPTBrokerError`, etc.)
- Unit test suite with `MockBroker` (zero cloud deps)

### Planned for 0.2.0
- `VaultBroker` — HashiCorp Vault (`ipt[vault]`)
- `SupabaseJWTBroker` — JWT + RLS (`ipt[supabase]`)
- `SupabaseAuditLedger`
- `CloudWatchAuditLedger`
- GitHub Actions CI
