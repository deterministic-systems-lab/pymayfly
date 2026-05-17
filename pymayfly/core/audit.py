"""
Audit ledger interface and built-in implementations.

The AuditLedger records every transaction open, close, and failure.
The library ships with:
  - ConsoleAuditLedger  (default, zero deps, useful for development)
  - FileAuditLedger     (append-only JSONL, zero deps)

Provider-specific ledgers:
  - SupabaseAuditLedger -- planned
  - CloudWatchAuditLedger -- planned
"""

from __future__ import annotations

import json
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path

from .provenance import ProvenanceRecord


class AuditLedger(ABC):
    """
    Abstract base class for IPT audit ledgers.

    Implementations must be append-only. Records must never be
    modified after writing. Deletion is out of scope for this
    interface — retention policy is the operator's responsibility.
    """

    @abstractmethod
    def open_transaction(self, record: ProvenanceRecord) -> None:
        """Write the initial record when a transaction opens."""
        ...

    @abstractmethod
    def close_transaction(self, record: ProvenanceRecord) -> None:
        """Update the record when a transaction closes successfully."""
        ...

    @abstractmethod
    def record_failure(self, record: ProvenanceRecord, error: str) -> None:
        """Update the record when a transaction fails."""
        ...


class ConsoleAuditLedger(AuditLedger):
    """
    Writes audit records to stdout as JSON lines.

    Zero dependencies. Suitable for development and testing.
    Not suitable for production — logs are not persisted.
    """

    def open_transaction(self, record: ProvenanceRecord) -> None:
        self._write("OPEN", record)

    def close_transaction(self, record: ProvenanceRecord) -> None:
        record.status = "closed"
        record.closed_at = int(time.time())
        self._write("CLOSE", record)

    def record_failure(self, record: ProvenanceRecord, error: str) -> None:
        record.status = "failed"
        record.closed_at = int(time.time())
        record.error = error
        self._write("FAIL", record)

    def _write(self, event: str, record: ProvenanceRecord) -> None:
        entry = {"event": event, "sha256": record.sha256(), **record.to_dict()}
        print(json.dumps(entry), file=sys.stdout, flush=True)


class FileAuditLedger(AuditLedger):
    """
    Appends audit records to a JSONL file.

    Zero dependencies. Suitable for single-process pipelines where
    a persistent local log is acceptable. For distributed pipelines,
    use a network-backed ledger.

    Args:
        path: Path to the JSONL log file. Created if it does not exist.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def open_transaction(self, record: ProvenanceRecord) -> None:
        self._append("OPEN", record)

    def close_transaction(self, record: ProvenanceRecord) -> None:
        record.status = "closed"
        record.closed_at = int(time.time())
        self._append("CLOSE", record)

    def record_failure(self, record: ProvenanceRecord, error: str) -> None:
        record.status = "failed"
        record.closed_at = int(time.time())
        record.error = error
        self._append("FAIL", record)

    def _append(self, event: str, record: ProvenanceRecord) -> None:
        entry = {"event": event, "sha256": record.sha256(), **record.to_dict()}
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
