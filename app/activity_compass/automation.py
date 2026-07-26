from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from .db import Database


class MaintenanceWorker:
    """Run safe local maintenance without changing user-authored dates."""

    def __init__(self, db: Database, interval_seconds: int = 60):
        self.db = db
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="activity-maintenance")
        self.last_backup_date: str | None = None

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.db.apply_automatic_rules()
            today = datetime.now().strftime("%Y-%m-%d")
            if self.last_backup_date != today:
                backup_dir = self.db.path.parent / "backups"
                self.db.backup(backup_dir / f"activity-{today}.db")
                self._prune(backup_dir, keep=14)
                self.last_backup_date = today
            self.stop_event.wait(self.interval_seconds)

    @staticmethod
    def _prune(folder: Path, keep: int) -> None:
        files = sorted(folder.glob("activity-*.db"), reverse=True)
        for old in files[keep:]:
            old.unlink(missing_ok=True)
