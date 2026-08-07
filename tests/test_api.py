import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from activity_compass.api import start_api
from activity_compass.db import Database


class ApiEncodingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.db")
        self.server, self.thread = start_api(self.db, 0)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def post_json(self, path: str, payload: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def get_json(self, path: str) -> tuple[int, dict, dict]:
        with urllib.request.urlopen(self.base_url + path, timeout=2) as response:
            return (
                response.status,
                json.loads(response.read().decode("utf-8")),
                dict(response.headers),
            )

    def test_utf8_round_trip(self) -> None:
        status, body = self.post_json(
            "/v1/items",
            {
                "entity_type": "task",
                "title": "現実改変の運用仕様を定義",
                "details": "日本語をUTF-8のまま保存する。",
            },
        )

        self.assertEqual(status, 201)
        self.assertEqual(body["title"], "現実改変の運用仕様を定義")
        self.assertEqual(body["details"], "日本語をUTF-8のまま保存する。")

    def test_rejects_lossy_question_mark_runs(self) -> None:
        status, body = self.post_json(
            "/v1/items",
            {"entity_type": "task", "title": "????????????"},
        )

        self.assertEqual(status, 400)
        self.assertIn("appears corrupted", body["error"])
        self.assertEqual(self.db.list_items(), [])

    def test_change_token_advances_after_api_write(self) -> None:
        _, before, _ = self.get_json("/v1/changes")

        status, _ = self.post_json(
            "/v1/items",
            {"entity_type": "task", "title": "自動更新を確認する"},
        )
        _, after, _ = self.get_json("/v1/changes")

        self.assertEqual(status, 201)
        self.assertGreater(after["token"], before["token"])

    def test_partial_update_auto_saves_details_without_changing_other_fields(self) -> None:
        _, created = self.post_json(
            "/v1/items",
            {
                "entity_type": "project",
                "title": "自動保存対象",
                "status": "in_progress",
                "details": "変更前",
            },
        )

        status, updated = self.post_json(
            f"/v1/items/{created['id']}",
            {"details": "入力直後に保存"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(updated["details"], "入力直後に保存")
        self.assertEqual(updated["title"], "自動保存対象")
        self.assertEqual(updated["status"], "in_progress")

    def test_get_responses_disable_caching(self) -> None:
        status, _, headers = self.get_json("/v1/items?view=all")

        self.assertEqual(status, 200)
        self.assertIn("no-store", headers["Cache-Control"])

    def test_health_reports_api_schema_version(self) -> None:
        status, body, _ = self.get_json("/health")

        self.assertEqual(status, 200)
        self.assertEqual(body["api_schema_version"], 4)


if __name__ == "__main__":
    unittest.main()
