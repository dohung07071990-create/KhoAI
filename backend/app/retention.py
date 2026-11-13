"""Retention jobs for audit records, incidents and evidence files."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from .services.retention_worker import RetentionWorker


class RetentionService:
    def __init__(self, db_session: Callable[[], Any], business_tz: Any, logger: logging.Logger) -> None:
        self.db_session = db_session
        self.business_tz = business_tz
        self.logger = logger
        from .services.audit_retention import AuditRetentionService
        from .services.evidence_retention import EvidenceRetentionService
        self._audit_retention = AuditRetentionService(db_session, business_tz)
        self._evidence_retention = EvidenceRetentionService(db_session, business_tz, logger)
        self._worker = RetentionWorker(self.prune_old_logs, logger)

    def prune_old_logs(self, retention_days: int | None = None) -> dict[str, int]:
        audit_result = self._audit_retention.prune_old_logs(retention_days)
        evidence_deleted = self.prune_evidence_files()
        return {**audit_result, "evidence_files_deleted": evidence_deleted}

    def prune_evidence_files(self, evidence_dir: Path | None = None) -> int:
        return self._evidence_retention.prune_evidence_files(evidence_dir)

    def mark_evidence_expired(self, filename: str) -> int:
        return self._evidence_retention.mark_evidence_expired(filename)

    async def worker(self) -> None:
        await self._worker.run_forever()
