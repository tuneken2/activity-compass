from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from .db import Database
from .notifications import show_windows_notification

REMINDER_TITLES = {
    "due": "期限になりました",
    "scheduled": "予定の時間になりました",
}


class MaintenanceWorker:
    """Run safe local maintenance without changing user-authored dates."""

    def __init__(
        self,
        db: Database,
        interval_seconds: int = 60,
        notifier: Callable[[str, str], None] | None = None,
    ):
        self.db = db
        self.interval_seconds = interval_seconds
        self.notifier = notifier or show_windows_notification
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
            self._send_due_notifications()
            today = datetime.now().strftime("%Y-%m-%d")
            if self.last_backup_date != today:
                backup_dir = self.db.path.parent / "backups"
                self.db.backup(backup_dir / f"activity-{today}.db")
                self._prune(backup_dir, keep=14)
                self.last_backup_date = today
            self.stop_event.wait(self.interval_seconds)

    def _send_due_notifications(self) -> None:
        for reminder in self.db.due_notifications():
            title = REMINDER_TITLES.get(reminder["trigger_kind"], "お知らせ")
            self.notifier(title, reminder["title"])
            self.db.mark_notified(reminder["id"], reminder["trigger_key"])

    @staticmethod
    def _prune(folder: Path, keep: int) -> None:
        files = sorted(folder.glob("activity-*.db"), reverse=True)
        for old in files[keep:]:
            old.unlink(missing_ok=True)
