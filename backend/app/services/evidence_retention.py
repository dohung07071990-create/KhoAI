"""Evidence-file retention and persisted evidence-reference lifecycle."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


class EvidenceRetentionService:
    def __init__(self, db_session: Callable[[], Any], business_tz: Any, logger: logging.Logger) -> None:
        self.db_session = db_session
        self.business_tz = business_tz
        self.logger = logger

    def prune_evidence_files(self, evidence_dir: Path | None = None) -> int:
        """Apply age/size retention without deleting evidence linked to an open incident."""
        if evidence_dir is None:
            try:
                from ai.person_detector import EVIDENCE_DIR
                evidence_dir = EVIDENCE_DIR
            except Exception:
                return 0
        if not evidence_dir.is_dir():
            return 0
        max_age_days = max(1, int(os.getenv("KHOAI_EVIDENCE_MAX_AGE_DAYS", "30")))
        max_bytes = max(1, int(os.getenv("KHOAI_EVIDENCE_MAX_BYTES", str(2 * 1024 * 1024 * 1024))))
        cutoff_ts = time.time() - max_age_days * 86400
        protected: set[str] = set()
        with self.db_session() as db:
            rows = db.execute("""SELECT ie.details_json FROM incident_events ie
                JOIN incidents i ON i.incident_id=ie.incident_id WHERE i.status='OPEN'""").fetchall()
        for row in rows:
            try:
                details = json.loads(row["details_json"] or "{}")
                filename = details.get("evidence_filename")
                url = details.get("evidence_url")
                if filename:
                    protected.add(Path(str(filename)).name)
                elif url:
                    protected.add(str(url).rsplit("/", 1)[-1])
            except (TypeError, ValueError):
                continue
        files = sorted((p for p in evidence_dir.glob("*.jpg") if p.is_file()), key=lambda p: p.stat().st_mtime)
        total_bytes = sum(p.stat().st_size for p in files)
        deleted = 0
        for path in files:
            if path.name in protected:
                continue
            too_old = path.stat().st_mtime < cutoff_ts
            over_quota = total_bytes > max_bytes
            if too_old or over_quota:
                size = path.stat().st_size
                try:
                    path.unlink()
                except OSError:
                    self.logger.warning("Không xóa được evidence cũ: %s", path)
                    continue
                try:
                    self.mark_evidence_expired(path.name)
                except Exception:
                    # File retention must continue, but the missing metadata is logged
                    # so operators can identify stale evidence references.
                    self.logger.exception("Không cập nhật được metadata evidence đã hết hạn: %s", path.name)
                total_bytes -= size
                deleted += 1
        if total_bytes > max_bytes:
            self.logger.error("Evidence vượt hạn mức %s bytes; phần còn lại đang được incident OPEN tham chiếu.", max_bytes)
        return deleted

    def mark_evidence_expired(self, filename: str) -> int:
        """Mark persisted event references as expired after their image is removed."""
        if not filename or Path(filename).name != filename:
            return 0
        expired_at = datetime.now(self.business_tz).isoformat(timespec="seconds")
        updated = 0
        with self.db_session() as db:
            for table in ("security_events", "incident_events"):
                rows = db.execute(f"SELECT id, details_json FROM {table} WHERE details_json LIKE ?",
                                  (f"%{filename}%",)).fetchall()
                for row in rows:
                    try:
                        details = json.loads(row["details_json"] or "{}")
                    except (TypeError, ValueError):
                        continue
                    stored_name = details.get("evidence_filename")
                    url = details.get("evidence_url")
                    if stored_name != filename and (not isinstance(url, str) or url.rsplit("/", 1)[-1] != filename):
                        continue
                    details["evidence_filename"] = filename
                    details["evidence_url"] = None
                    details["evidence_expired"] = True
                    details["evidence_status"] = "expired"
                    details["evidence_expired_at"] = expired_at
                    db.execute(f"UPDATE {table} SET details_json=? WHERE id=?",
                               (json.dumps(details, ensure_ascii=False), row["id"]))
                    updated += 1
        return updated
