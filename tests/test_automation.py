import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from activity_compass.automation import MaintenanceWorker
from activity_compass.db import Database


class MaintenanceWorkerNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.db")
        self.sent: list[tuple[str, str]] = []
        self.worker = MaintenanceWorker(
            self.db, notifier=lambda title, message: self.sent.append((title, message))
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sends_a_notification_for_a_past_due_item(self) -> None:
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        item = self.db.create_item(
            {"title": "期限を過ぎた作業", "entity_type": "task", "due_at": past}
        )

        self.worker._send_due_notifications()

        self.assertEqual(self.sent, [("期限になりました", item["title"])])

    def test_sends_separate_notifications_for_due_and_scheduled(self) -> None:
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        item = self.db.create_item(
            {
                "title": "期限も予定もある作業",
                "entity_type": "task",
                "due_at": past,
                "scheduled_at": past,
            }
        )

        self.worker._send_due_notifications()

        self.assertEqual(
            sorted(self.sent),
            sorted(
                [
                    ("期限になりました", item["title"]),
                    ("予定の時間になりました", item["title"]),
                ]
            ),
        )

    def test_does_not_repeat_a_notification_already_sent(self) -> None:
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        self.db.create_item(
            {"title": "一度だけ通知される作業", "entity_type": "task", "due_at": past}
        )

        self.worker._send_due_notifications()
        self.worker._send_due_notifications()

        self.assertEqual(len(self.sent), 1)

    def test_does_not_notify_when_there_is_nothing_due(self) -> None:
        future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        self.db.create_item(
            {"title": "まだ先の作業", "entity_type": "task", "due_at": future}
        )

        self.worker._send_due_notifications()

        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
