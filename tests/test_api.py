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


if __name__ == "__main__":
    unittest.main()
