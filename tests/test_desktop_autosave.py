import unittest
from pathlib import Path


class DesktopAutoSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (
            Path(__file__).resolve().parents[1] / "desktop.hta"
        ).read_text(encoding="utf-8")

    def test_details_input_schedules_auto_save(self) -> None:
        self.assertIn(
            'id="editDetails" oninput="scheduleDetailAutoSave()"',
            self.html,
        )
        self.assertIn("function scheduleDetailAutoSave()", self.html)
        self.assertIn("}, 120);", self.html)
        self.assertIn("pending.payload", self.html)

    def test_every_editable_field_triggers_auto_save(self) -> None:
        for marker in (
            'id="editTitle" oninput="scheduleDetailAutoSave()"',
            'id="editType" onchange="scheduleDetailAutoSave()"',
            'id="editStatus" onchange="scheduleDetailAutoSave()"',
            'id="editCategory" oninput="scheduleDetailAutoSave()"',
            'id="editProjectRank" type="number" min="1" step="1" oninput="scheduleDetailAutoSave()"',
            'id="editParentProject" onchange="scheduleDetailAutoSave()"',
            'id="editProject" onchange="scheduleDetailAutoSave()"',
            'id="editEffort" onchange="scheduleDetailAutoSave()"',
            'id="editPriority" type="number" min="1" max="3" step="1" oninput="scheduleDetailAutoSave()"',
        ):
            self.assertIn(marker, self.html)
        # editScheduled appears once for anime/manga and once for everything
        # else; both variants must auto-save.
        self.assertEqual(
            self.html.count('id="editScheduled" oninput="scheduleDetailAutoSave()"'),
            2,
        )
        self.assertEqual(
            self.html.count('id="editDue" oninput="scheduleDetailAutoSave()"'),
            1,
        )

    def test_auto_save_and_manual_save_share_the_same_payload_builder(self) -> None:
        self.assertIn("function buildEditPayload(entityType)", self.html)
        self.assertIn("var payload = buildEditPayload(detailAutoSaveEntityType);", self.html)
        self.assertIn("var payload = buildEditPayload(row.entity_type);", self.html)
        self.assertIn("function payloadsEqual(a, b)", self.html)

    def test_manual_save_and_save_state_remain_visible(self) -> None:
        self.assertIn('onclick="saveItem()">保存</button>', self.html)
        self.assertIn('id="detailSaveState"', self.html)
        self.assertIn("自動保存: 保存済み", self.html)
        self.assertIn("自動保存に失敗しました。保存ボタンを押してください。", self.html)

    def test_auto_save_has_a_polling_fallback_for_missed_input_events(self) -> None:
        # mshta's legacy IE engine can miss oninput while composing text
        # through an IME, so a periodic check must catch any unsaved change.
        self.assertIn("function watchDetailAutoSave()", self.html)
        self.assertIn("setInterval(watchDetailAutoSave, 1000);", self.html)
        self.assertIn("queueCurrentDetailSave();", self.html)


if __name__ == "__main__":
    unittest.main()
