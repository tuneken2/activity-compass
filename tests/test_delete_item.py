import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from activity_compass.api import start_api
from activity_compass.db import Database


class DeleteItemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_delete_item_removes_task_and_records_history(self) -> None:
        item = self.db.create_item({"title": "削除対象", "entity_type": "task"})

        result = self.db.delete_item(item["id"])

        self.assertTrue(result["deleted"])
        self.assertEqual(self.db.list_items("all"), [])
        event = self.db.list_history()[0]
        self.assertEqual(event["action"], "delete")
        self.assertEqual(json.loads(event["payload_json"])["title"], "削除対象")

    def test_deleting_project_keeps_children_as_unassigned_items(self) -> None:
        project = self.db.create_item(
            {"title": "削除するプロジェクト", "entity_type": "project"}
        )
        task = self.db.create_item(
            {
                "title": "残すタスク",
                "entity_type": "task",
                "project_id": project["id"],
            }
        )

        self.db.delete_item(project["id"])

        self.assertIsNone(self.db.get_item(task["id"])["project_id"])

    def test_delete_endpoint_removes_item(self) -> None:
        item = self.db.create_item({"title": "API削除対象", "entity_type": "task"})
        server, thread = start_api(self.db, 0)
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/v1/items/{item['id']}/delete",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertTrue(payload["deleted"])
            self.assertEqual(self.db.list_items("all"), [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class DesktopDeleteConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (
            Path(__file__).resolve().parents[1] / "desktop.hta"
        ).read_text(encoding="utf-8")

    def test_detail_has_delete_button_and_confirmation(self) -> None:
        self.assertIn(
            'onclick="confirmDeleteItem()">削除</button>',
            self.html,
        )
        self.assertIn("function confirmDeleteItem()", self.html)
        self.assertIn("この操作は元に戻せません。", self.html)
        self.assertIn("if (!confirm(message)) return;", self.html)


if __name__ == "__main__":
    unittest.main()
