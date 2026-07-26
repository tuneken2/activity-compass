import tempfile
import unittest
from pathlib import Path

from activity_compass.db import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_and_list(self) -> None:
        created = self.db.create_item({"title": "見積もりを確認", "entity_type": "task"})
        self.assertEqual(created["title"], "見積もりを確認")
        self.assertEqual(len(self.db.list_items("next")), 1)

    def test_sync_is_idempotent(self) -> None:
        payload = {
            "idempotency_key": "conversation-1:message-4",
            "events": [
                {
                    "action": "create",
                    "entity_type": "idea",
                    "title": "会話同期アプリ",
                    "confidence": 0.97,
                }
            ],
        }
        first = self.db.sync(payload)
        second = self.db.sync(payload)
        self.assertEqual(first["created"], 1)
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(self.db.list_items()), 1)

    def test_low_confidence_completion_requires_review(self) -> None:
        item = self.db.create_item({"title": "発注する", "entity_type": "task"})
        result = self.db.sync(
            {
                "events": [
                    {
                        "action": "complete",
                        "entity_type": "task",
                        "target_id": item["id"],
                        "title": "発注する",
                        "confidence": 0.7,
                    }
                ]
            }
        )
        self.assertEqual(result["review"], 1)
        self.assertEqual(self.db.get_item(item["id"])["status"], "inbox")
        review = self.db.list_reviews()[0]
        self.db.resolve_review(review["id"], True)
        self.assertEqual(self.db.get_item(item["id"])["status"], "done")

    def test_search_update_and_backup(self) -> None:
        item = self.db.create_item(
            {"title": "札幌ホテル候補", "entity_type": "task", "details": "駅の近く"}
        )
        self.assertEqual(len(self.db.search_items("札幌 駅")), 1)
        updated = self.db.update_item(item["id"], {"details": "大通駅の近く"})
        self.assertEqual(updated["details"], "大通駅の近く")
        backup = self.db.backup(Path(self.temp_dir.name) / "backup" / "copy.db")
        self.assertTrue(backup.exists())

    def test_due_item_is_promoted_to_today(self) -> None:
        item = self.db.create_item(
            {
                "title": "今日が期限",
                "entity_type": "task",
                "status": "next",
                "due_at": "2020-01-01",
            }
        )
        self.assertEqual(self.db.apply_automatic_rules(), 1)
        self.assertEqual(self.db.get_item(item["id"])["status"], "today")

    def test_task_priority_uses_project_deadline_and_effort(self) -> None:
        project = self.db.create_item(
            {"title": "優先プロジェクト", "entity_type": "project", "priority": 2}
        )
        hard = self.db.create_item(
            {
                "title": "高工数タスク",
                "entity_type": "task",
                "project_id": project["id"],
                "effort": 5,
            }
        )
        urgent = self.db.create_item(
            {
                "title": "高工数だが期限が近いタスク",
                "entity_type": "task",
                "project_id": project["id"],
                "effort": 5,
                "due_at": "2020-01-01",
            }
        )

        self.assertEqual(hard["priority"], 1)
        self.assertEqual(urgent["priority"], 2)
        self.assertIn("優先プロジェクト", urgent["priority_reason"])
        self.assertIn("高工数", urgent["priority_reason"])

    def test_sync_links_items_to_project_created_in_same_batch(self) -> None:
        self.db.sync(
            {
                "events": [
                    {
                        "action": "create",
                        "entity_type": "project",
                        "title": "会話内プロジェクト",
                        "priority": 3,
                        "confidence": 0.99,
                    },
                    {
                        "action": "create",
                        "entity_type": "task",
                        "title": "会話内タスク",
                        "confidence": 0.99,
                    },
                ]
            }
        )
        project = self.db.search_items("会話内プロジェクト")[0]
        task = self.db.search_items("会話内タスク")[0]
        self.assertEqual(task["project_id"], project["id"])
        self.assertEqual(task["priority"], 3)

    def test_projects_include_root_group_for_parent_filtering(self) -> None:
        root = self.db.create_item(
            {"title": "親プロジェクト", "entity_type": "project", "priority": 3}
        )
        child = self.db.create_item(
            {
                "title": "子プロジェクト",
                "entity_type": "project",
                "parent_project_id": root["id"],
                "priority": 2,
            }
        )
        projects = {item["id"]: item for item in self.db.list_items("projects")}
        self.assertEqual(projects[child["id"]]["root_project_id"], root["id"])
        self.assertEqual(
            projects[child["id"]]["root_project_title"], root["title"]
        )
        self.assertEqual(self.db.counts()["projects"], 2)

    def test_project_tasks_view_returns_tasks_grouped_under_projects(self) -> None:
        project = self.db.create_item(
            {"title": "展開対象プロジェクト", "entity_type": "project"}
        )
        child = self.db.create_item(
            {
                "title": "表示される子タスク",
                "entity_type": "task",
                "project_id": project["id"],
            }
        )
        self.db.create_item(
            {"title": "所属なしタスク", "entity_type": "task"}
        )

        project_tasks = self.db.list_items("project_tasks")

        self.assertEqual([item["id"] for item in project_tasks], [child["id"]])
        self.assertEqual(project_tasks[0]["project_title"], project["title"])

    def test_project_priority_can_be_read_from_overview(self) -> None:
        project = self.db.create_item(
            {
                "title": "概要基準プロジェクト",
                "entity_type": "project",
                "details": "優先順位1。本業とともに最優先で進める。",
            }
        )
        self.assertEqual(project["priority"], 3)
        self.assertIn("概要基準", project["priority_reason"])

    def test_project_category_is_saved_and_inherited_by_tasks(self) -> None:
        project = self.db.create_item(
            {
                "title": "顧客向けアプリ",
                "entity_type": "project",
                "category": "仕事",
                "category_color": "#527792",
            }
        )
        self.db.create_item(
            {
                "title": "画面を実装する",
                "entity_type": "task",
                "project_id": project["id"],
            }
        )

        task = self.db.list_items("project_tasks")[0]
        self.assertEqual(project["category"], "仕事")
        self.assertEqual(project["category_color"], "#527792")
        self.assertEqual(task["project_category"], "仕事")
        self.assertEqual(task["project_category_color"], "#527792")

    def test_same_category_reuses_and_updates_its_color(self) -> None:
        first = self.db.create_item(
            {
                "title": "第一プロジェクト",
                "entity_type": "project",
                "category": "個人開発",
                "category_color": "#7E5D8D",
            }
        )
        second = self.db.create_item(
            {
                "title": "第二プロジェクト",
                "entity_type": "project",
                "category": "個人開発",
            }
        )
        self.assertEqual(second["category_color"], "#7E5D8D")

        self.db.update_item(
            second["id"],
            {"category": "個人開発", "category_color": "#B15939"},
        )
        self.assertEqual(self.db.get_item(first["id"])["category_color"], "#B15939")

    def test_invalid_project_category_color_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid category color"):
            self.db.create_item(
                {
                    "title": "不正色プロジェクト",
                    "entity_type": "project",
                    "category": "仕事",
                    "category_color": "red",
                }
            )

    def test_projects_have_dense_rank_within_each_priority(self) -> None:
        first = self.db.create_item(
            {
                "title": "高優先度の先行プロジェクト",
                "entity_type": "project",
                "priority": 3,
            }
        )
        second = self.db.create_item(
            {
                "title": "高優先度の後続プロジェクト",
                "entity_type": "project",
                "priority": 3,
            }
        )
        low = self.db.create_item(
            {
                "title": "低優先度プロジェクト",
                "entity_type": "project",
                "priority": 1,
            }
        )

        self.assertEqual(first["project_rank"], 1)
        self.assertEqual(second["project_rank"], 2)
        self.assertEqual(low["project_rank"], 1)

        self.db.update_item(second["id"], {"project_rank": 1})
        projects = self.db.list_items("projects")
        self.assertEqual(
            [item["id"] for item in projects],
            [second["id"], first["id"], low["id"]],
        )
        self.assertEqual(self.db.get_item(first["id"])["project_rank"], 2)

    def test_project_rank_must_be_a_positive_integer(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive integer"):
            self.db.create_item(
                {
                    "title": "不正序列プロジェクト",
                    "entity_type": "project",
                    "priority": 2,
                    "project_rank": 0,
                }
            )

    def test_manual_priority_accepts_only_numbers_one_to_three(self) -> None:
        project = self.db.create_item(
            {
                "title": "数値優先度プロジェクト",
                "entity_type": "project",
                "priority": "3",
            }
        )
        self.assertEqual(project["priority"], 3)
        with self.assertRaisesRegex(ValueError, "1 to 3"):
            self.db.update_item(project["id"], {"priority": "高"})

    def test_sync_can_update_project_category(self) -> None:
        project = self.db.create_item(
            {"title": "分類対象", "entity_type": "project"}
        )
        result = self.db.sync(
            {
                "events": [
                    {
                        "action": "update",
                        "entity_type": "project",
                        "target_id": project["id"],
                        "title": project["title"],
                        "category": "学習",
                        "category_color": "#657547",
                        "confidence": 0.99,
                    }
                ]
            }
        )

        updated = self.db.get_item(project["id"])
        self.assertEqual(result["updated"], 1)
        self.assertEqual(updated["category"], "学習")
        self.assertEqual(updated["category_color"], "#657547")


if __name__ == "__main__":
    unittest.main()
