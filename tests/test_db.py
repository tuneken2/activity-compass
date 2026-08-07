import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
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

    def test_anime_and_manga_have_a_dedicated_view(self) -> None:
        anime = self.db.create_item(
            {
                "title": "配信作品",
                "entity_type": "anime",
                "scheduled_at": "毎週月曜 24:00",
            }
        )
        manga = self.db.create_item(
            {
                "title": "発売作品",
                "entity_type": "manga",
                "scheduled_at": "2026-08-03",
            }
        )
        self.db.create_item({"title": "通常タスク", "entity_type": "task"})

        media = self.db.list_items("anime_manga")

        self.assertEqual({item["id"] for item in media}, {anime["id"], manga["id"]})
        self.assertEqual(self.db.counts()["anime_manga"], 2)

    def test_legacy_anime_project_is_migrated_and_removed(self) -> None:
        project = self.db.create_item(
            {
                "title": "アニメ",
                "entity_type": "project",
                "details": "視聴するアニメを管理するプロジェクト。",
            }
        )
        child = self.db.create_item(
            {
                "title": "作品名｜Netflix・毎週水曜24:00以降",
                "entity_type": "task",
                "details": "視聴タスク。",
                "project_id": project["id"],
            }
        )
        with self.db.connect() as connection:
            connection.execute(
                "DELETE FROM app_migrations WHERE name = ?",
                ("2026-07-27-anime-manga-view",),
            )

        reopened = Database(self.db.path)
        migrated = reopened.get_item(child["id"])

        self.assertEqual(migrated["entity_type"], "anime")
        self.assertEqual(migrated["title"], "作品名")
        self.assertEqual(migrated["scheduled_at"], "毎週水曜24:00以降")
        self.assertIn("配信サービス: Netflix", migrated["details"])
        self.assertIsNone(migrated["project_id"])
        self.assertEqual(reopened.list_items("projects"), [])
        with self.assertRaises(KeyError):
            reopened.get_item(project["id"])

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

    def test_today_excludes_project_ancestors(self) -> None:
        root = self.db.create_item(
            {
                "title": "親プロジェクト",
                "entity_type": "project",
                "status": "inbox",
            }
        )
        project = self.db.create_item(
            {
                "title": "子プロジェクト",
                "entity_type": "project",
                "status": "inbox",
                "parent_project_id": root["id"],
            }
        )
        task = self.db.create_item(
            {
                "title": "進行中の作業",
                "entity_type": "task",
                "status": "in_progress",
                "project_id": project["id"],
                "due_at": "2020-01-01",
            }
        )

        today_ids = {item["id"] for item in self.db.list_items("today")}

        self.assertEqual(today_ids, {task["id"]})

    def test_today_excludes_tasks_with_no_due_or_scheduled_date(self) -> None:
        no_date_but_marked_today = self.db.create_item(
            {"title": "無期限の今日タスク", "entity_type": "task", "status": "today"}
        )
        no_date_in_progress = self.db.create_item(
            {"title": "無期限の進行中タスク", "entity_type": "task", "status": "in_progress"}
        )

        today_ids = {item["id"] for item in self.db.list_items("today")}

        self.assertNotIn(no_date_but_marked_today["id"], today_ids)
        self.assertNotIn(no_date_in_progress["id"], today_ids)

    def test_today_includes_due_today_and_overdue_but_not_future(self) -> None:
        overdue = self.db.create_item(
            {"title": "期限切れタスク", "entity_type": "task", "due_at": "2020-01-01"}
        )
        due_today = self.db.create_item(
            {
                "title": "本日期限タスク",
                "entity_type": "task",
                "due_at": date.today().isoformat(),
            }
        )
        scheduled_today = self.db.create_item(
            {
                "title": "本日予定タスク",
                "entity_type": "task",
                "scheduled_at": date.today().isoformat(),
            }
        )
        future = self.db.create_item(
            {
                "title": "先の予定タスク",
                "entity_type": "task",
                "due_at": (date.today() + timedelta(days=3)).isoformat(),
            }
        )

        today_ids = {item["id"] for item in self.db.list_items("today")}

        self.assertIn(overdue["id"], today_ids)
        self.assertIn(due_today["id"], today_ids)
        self.assertIn(scheduled_today["id"], today_ids)
        self.assertNotIn(future["id"], today_ids)

    def test_task_lists_show_projects_only_in_project_view(self) -> None:
        statuses = ("today", "in_progress", "next", "waiting", "someday", "done")
        projects = {}
        tasks = {}
        for status in statuses:
            projects[status] = self.db.create_item(
                {
                    "title": f"{status} project",
                    "entity_type": "project",
                    "status": status,
                }
            )
            tasks[status] = self.db.create_item(
                {
                    "title": f"{status} task",
                    "entity_type": "task",
                    "status": status,
                    # "today" now requires an actual due/scheduled date; a
                    # past date keeps this task visible in every view under
                    # test without affecting the others.
                    "due_at": "2020-01-01",
                }
            )

        for view in statuses:
            item_ids = {item["id"] for item in self.db.list_items(view)}
            self.assertIn(tasks[view]["id"], item_ids)
            self.assertNotIn(projects[view]["id"], item_ids)

        self.assertEqual(
            {item["id"] for item in self.db.list_items("projects")},
            {project["id"] for project in projects.values() if project["status"] != "done"},
        )
        self.assertTrue(
            {item["id"] for item in self.db.list_items("all_items")}.isdisjoint(
                {project["id"] for project in projects.values()}
            )
        )

    def test_today_excludes_anime_even_when_in_progress_or_due(self) -> None:
        in_progress = self.db.create_item(
            {
                "title": "進行中のアニメ",
                "entity_type": "anime",
                "status": "in_progress",
            }
        )
        due = self.db.create_item(
            {
                "title": "配信日を過ぎたアニメ",
                "entity_type": "anime",
                "status": "today",
                "scheduled_at": "2020-01-01",
            }
        )

        today_ids = {item["id"] for item in self.db.list_items("today")}

        self.assertNotIn(in_progress["id"], today_ids)
        self.assertNotIn(due["id"], today_ids)

    def test_today_includes_anime_only_on_its_streaming_weekday(self) -> None:
        weekdays = ("月曜", "火曜", "水曜", "木曜", "金曜", "土曜", "日曜")
        today_index = date.today().weekday()
        today_anime = self.db.create_item(
            {
                "title": "本日配信のアニメ",
                "entity_type": "anime",
                "status": "in_progress",
                "scheduled_at": f"毎週{weekdays[today_index]} 24:00",
            }
        )
        other_day_anime = self.db.create_item(
            {
                "title": "別曜日配信のアニメ",
                "entity_type": "anime",
                "status": "in_progress",
                "scheduled_at": f"毎週{weekdays[(today_index + 1) % 7]} 24:00",
            }
        )

        today_ids = {item["id"] for item in self.db.list_items("today")}

        self.assertIn(today_anime["id"], today_ids)
        self.assertNotIn(other_day_anime["id"], today_ids)

    def test_in_progress_excludes_anime(self) -> None:
        anime = self.db.create_item(
            {
                "title": "進行中のアニメ",
                "entity_type": "anime",
                "status": "in_progress",
            }
        )
        task = self.db.create_item(
            {
                "title": "進行中の作業",
                "entity_type": "task",
                "status": "in_progress",
            }
        )

        in_progress_ids = {
            item["id"] for item in self.db.list_items("in_progress")
        }

        self.assertEqual(in_progress_ids, {task["id"]})
        self.assertNotIn(anime["id"], in_progress_ids)

    def test_in_progress_has_its_own_view(self) -> None:
        item = self.db.create_item(
            {
                "title": "進行中の作業",
                "entity_type": "task",
                "status": "in_progress",
            }
        )

        self.assertEqual(item["status"], "in_progress")
        self.assertEqual(
            [row["id"] for row in self.db.list_items("in_progress")], [item["id"]]
        )
        self.assertEqual(self.db.list_items("next"), [])

    def test_done_view_excludes_cancelled_items(self) -> None:
        done = self.db.create_item(
            {"title": "完了した作業", "entity_type": "task", "status": "done"}
        )
        self.db.create_item(
            {"title": "取り消した作業", "entity_type": "task", "status": "cancelled"}
        )

        self.assertEqual([row["id"] for row in self.db.list_items("done")], [done["id"]])

    def test_done_items_move_to_archive_after_two_weeks(self) -> None:
        recent = self.db.create_item(
            {"title": "最近完了した作業", "entity_type": "task", "status": "done"}
        )
        old = self.db.create_item(
            {"title": "昔完了した作業", "entity_type": "task", "status": "done"}
        )
        old_completed_at = (
            datetime.now(timezone.utc) - timedelta(days=20)
        ).isoformat(timespec="seconds")
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE items SET completed_at = ? WHERE id = ?",
                (old_completed_at, old["id"]),
            )

        self.assertEqual(
            [row["id"] for row in self.db.list_items("done")], [recent["id"]]
        )
        self.assertEqual(
            [row["id"] for row in self.db.list_items("archive")], [old["id"]]
        )
        self.assertEqual(self.db.counts()["done"], 1)

    def test_reopening_an_archived_item_clears_its_completed_at(self) -> None:
        item = self.db.create_item(
            {"title": "やり直す作業", "entity_type": "task", "status": "done"}
        )
        old_completed_at = (
            datetime.now(timezone.utc) - timedelta(days=20)
        ).isoformat(timespec="seconds")
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE items SET completed_at = ? WHERE id = ?",
                (old_completed_at, item["id"]),
            )
        self.assertEqual(len(self.db.list_items("archive")), 1)

        self.db.update_status(item["id"], "next")

        self.assertIsNone(self.db.get_item(item["id"])["completed_at"])
        self.assertEqual(self.db.list_items("archive"), [])
        self.assertEqual(self.db.list_items("done"), [])

    def test_all_items_view_excludes_done_items(self) -> None:
        done = self.db.create_item(
            {"title": "完了済みタスク", "entity_type": "task", "status": "done"}
        )
        active = self.db.create_item(
            {"title": "未完了タスク", "entity_type": "task"}
        )

        all_ids = {row["id"] for row in self.db.list_items("all_items")}

        self.assertNotIn(done["id"], all_ids)
        self.assertIn(active["id"], all_ids)

    def test_project_tasks_view_excludes_done_and_cancelled_children(self) -> None:
        project = self.db.create_item(
            {"title": "完了タスクを含むプロジェクト", "entity_type": "project"}
        )
        active = self.db.create_item(
            {
                "title": "進行中の子タスク",
                "entity_type": "task",
                "project_id": project["id"],
            }
        )
        self.db.create_item(
            {
                "title": "完了済みの子タスク",
                "entity_type": "task",
                "project_id": project["id"],
                "status": "done",
            }
        )
        self.db.create_item(
            {
                "title": "取消済みの子タスク",
                "entity_type": "task",
                "project_id": project["id"],
                "status": "cancelled",
            }
        )

        project_task_ids = {
            row["id"] for row in self.db.list_items("project_tasks")
        }

        self.assertEqual(project_task_ids, {active["id"]})

    def test_counts_include_in_progress_and_done(self) -> None:
        self.db.create_item(
            {"title": "進行中の作業", "entity_type": "task", "status": "in_progress"}
        )
        self.db.create_item(
            {"title": "完了した作業", "entity_type": "task", "status": "done"}
        )

        counts = self.db.counts()
        self.assertEqual(counts["in_progress"], 1)
        self.assertEqual(counts["done"], 1)

    def test_sync_updates_existing_project_when_event_type_is_task(self) -> None:
        project = self.db.create_item(
            {
                "title": "Activity Compass",
                "entity_type": "project",
                "details": "初期メモ",
            }
        )

        result = self.db.sync(
            {
                "events": [
                    {
                        "action": "update",
                        "entity_type": "task",
                        "title": "Activity Compass",
                        "status": "in_progress",
                        "confidence": 0.99,
                    }
                ]
            }
        )

        self.assertEqual(result["updated"], 1)
        self.assertEqual(len(self.db.list_items()), 1)
        updated = self.db.get_item(project["id"])
        self.assertEqual(updated["entity_type"], "project")
        self.assertEqual(updated["status"], "in_progress")

    def test_sync_matches_safe_project_suffix_variation(self) -> None:
        project = self.db.create_item(
            {"title": "Activity Compass", "entity_type": "project"}
        )

        result = self.db.sync(
            {
                "events": [
                    {
                        "action": "update",
                        "entity_type": "project",
                        "title": "Activity Compass プロジェクト",
                        "details": "既存案件の更新",
                        "confidence": 0.99,
                    }
                ]
            }
        )

        self.assertEqual(result["updated"], 1)
        self.assertEqual(len(self.db.list_items()), 1)
        self.assertEqual(self.db.get_item(project["id"])["details"], "既存案件の更新")

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
        self.assertEqual(task["project_image_color"], project["project_color"])

    def test_projects_receive_distinct_image_colors_automatically(self) -> None:
        first = self.db.create_item(
            {"title": "赤い企画", "entity_type": "project"}
        )
        second = self.db.create_item(
            {"title": "青い企画", "entity_type": "project"}
        )

        self.assertRegex(first["project_color"], r"^#[0-9A-F]{6}$")
        self.assertRegex(second["project_color"], r"^#[0-9A-F]{6}$")
        self.assertNotEqual(first["project_color"], second["project_color"])

    def test_existing_projects_are_backfilled_with_distinct_colors(self) -> None:
        first = self.db.create_item(
            {"title": "既存企画A", "entity_type": "project"}
        )
        second = self.db.create_item(
            {"title": "既存企画B", "entity_type": "project"}
        )
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE items SET project_color = NULL WHERE entity_type = 'project'"
            )

        migrated = Database(self.db.path)

        first_color = migrated.get_item(first["id"])["project_color"]
        second_color = migrated.get_item(second["id"])["project_color"]
        self.assertTrue(first_color)
        self.assertTrue(second_color)
        self.assertNotEqual(first_color, second_color)

    def test_item_converted_to_project_receives_an_image_color(self) -> None:
        item = self.db.create_item(
            {"title": "企画へ変更", "entity_type": "task"}
        )

        updated = self.db.update_item(item["id"], {"entity_type": "project"})

        self.assertRegex(updated["project_color"], r"^#[0-9A-F]{6}$")

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

    def test_link_service_and_url_round_trip_for_anime(self) -> None:
        item = self.db.create_item(
            {
                "title": "SPY×FAMILY",
                "entity_type": "anime",
                "link_service": "Netflix",
                "link_url": "https://www.netflix.com/title/81579479",
            }
        )
        self.assertEqual(item["link_service"], "Netflix")
        self.assertEqual(item["link_url"], "https://www.netflix.com/title/81579479")

        updated = self.db.update_item(
            item["id"],
            {
                "link_service": "dアニメストア",
                "link_url": "https://animestore.docomo.ne.jp/animestore/sc_d_pc?workId=12345",
            },
        )
        self.assertEqual(updated["link_service"], "dアニメストア")
        self.assertEqual(
            updated["link_url"],
            "https://animestore.docomo.ne.jp/animestore/sc_d_pc?workId=12345",
        )

    def test_sync_can_update_anime_link(self) -> None:
        anime = self.db.create_item(
            {"title": "配信リンク同期対象", "entity_type": "anime"}
        )
        result = self.db.sync(
            {
                "events": [
                    {
                        "action": "update",
                        "entity_type": "anime",
                        "target_id": anime["id"],
                        "title": anime["title"],
                        "link_service": "ABEMA",
                        "link_url": "https://abema.tv/video/title/00000",
                        "confidence": 0.99,
                    }
                ]
            }
        )

        updated = self.db.get_item(anime["id"])
        self.assertEqual(result["updated"], 1)
        self.assertEqual(updated["link_service"], "ABEMA")
        self.assertEqual(updated["link_url"], "https://abema.tv/video/title/00000")

    def test_reminder_trigger_defaults_missing_time_to_ten_am(self) -> None:
        trigger = Database._resolve_reminder_trigger("2026-08-05")
        self.assertEqual(trigger, datetime(2026, 8, 5, 10, 0))

    def test_reminder_trigger_uses_explicit_time_when_present(self) -> None:
        trigger = Database._resolve_reminder_trigger("2026-08-05 18:30")
        self.assertEqual(trigger, datetime(2026, 8, 5, 18, 30))

    def test_reminder_trigger_skips_missing_input(self) -> None:
        self.assertIsNone(Database._resolve_reminder_trigger(None))
        self.assertIsNone(Database._resolve_reminder_trigger(""))

    def test_reminder_trigger_skips_text_without_a_real_date(self) -> None:
        self.assertIsNone(Database._resolve_reminder_trigger("毎週月曜 24:00"))

    def test_due_and_scheduled_notify_as_separate_reminders(self) -> None:
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        item = self.db.create_item(
            {
                "title": "期限も予定もある作業",
                "entity_type": "task",
                "due_at": past,
                "scheduled_at": past,
            }
        )

        reminders = [
            r for r in self.db.due_notifications() if r["id"] == item["id"]
        ]

        self.assertEqual({r["trigger_kind"] for r in reminders}, {"due", "scheduled"})
        self.assertEqual(len({r["trigger_key"] for r in reminders}), 2)

    def test_due_notification_skips_future_dates_and_dateless_schedules(self) -> None:
        future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        future_item = self.db.create_item(
            {"title": "未来の予定", "entity_type": "task", "due_at": future}
        )
        no_date_item = self.db.create_item(
            {
                "title": "配信中アニメ",
                "entity_type": "anime",
                "scheduled_at": "毎週月曜 24:00",
            }
        )

        ids = {r["id"] for r in self.db.due_notifications()}

        self.assertNotIn(future_item["id"], ids)
        self.assertNotIn(no_date_item["id"], ids)

    def test_due_notification_excludes_done_and_cancelled_items(self) -> None:
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        done_item = self.db.create_item(
            {
                "title": "完了済みで期限超過",
                "entity_type": "task",
                "due_at": past,
                "status": "done",
            }
        )
        cancelled_item = self.db.create_item(
            {
                "title": "取消済みで期限超過",
                "entity_type": "task",
                "due_at": past,
                "status": "cancelled",
            }
        )

        ids = {r["id"] for r in self.db.due_notifications()}

        self.assertNotIn(done_item["id"], ids)
        self.assertNotIn(cancelled_item["id"], ids)

    def test_marking_a_reminder_notified_prevents_it_from_repeating(self) -> None:
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        item = self.db.create_item(
            {"title": "確認済みにする作業", "entity_type": "task", "due_at": past}
        )
        reminder = next(
            r for r in self.db.due_notifications() if r["id"] == item["id"]
        )

        self.db.mark_notified(item["id"], reminder["trigger_key"])

        remaining = [r for r in self.db.due_notifications() if r["id"] == item["id"]]
        self.assertEqual(remaining, [])


if __name__ == "__main__":
    unittest.main()
