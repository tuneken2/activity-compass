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
        self.assertIn("{details:pending.details}", self.html)

    def test_manual_save_and_save_state_remain_visible(self) -> None:
        self.assertIn('onclick="saveItem()">保存</button>', self.html)
        self.assertIn('id="detailSaveState"', self.html)
        self.assertIn("自動保存: 保存済み", self.html)
        self.assertIn("自動保存に失敗しました。保存ボタンを押してください。", self.html)


if __name__ == "__main__":
    unittest.main()
