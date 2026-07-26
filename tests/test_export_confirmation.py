import unittest
from pathlib import Path


class ExportConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (
            Path(__file__).resolve().parents[1] / "desktop.hta"
        ).read_text(encoding="utf-8")

    def test_export_button_opens_explanation_before_exporting(self) -> None:
        self.assertIn(
            'onclick="showExportConfirmation()">データを書き出す</button>',
            self.html,
        )
        self.assertIn("タスク、予定、プロジェクト、更新履歴", self.html)
        self.assertIn("現在のデータが変更・削除されることはありません", self.html)

    def test_confirmation_has_explicit_execute_and_cancel_actions(self) -> None:
        self.assertIn('onclick="cancelExport()">中止</button>', self.html)
        self.assertIn('onclick="executeExport()">実行</button>', self.html)
        self.assertIn('request("POST", "/v1/export"', self.html)


if __name__ == "__main__":
    unittest.main()
