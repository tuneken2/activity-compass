import unittest

from activity_compass.ui import TYPE_LABELS, format_list_date


class UiFormattingTests(unittest.TestCase):
    def test_project_label_uses_project_terminology(self) -> None:
        self.assertEqual(TYPE_LABELS["project"], "プロジェクト")

    def test_item_without_dates_is_indefinite(self) -> None:
        self.assertEqual(format_list_date(None, "予定"), ("無期限", "締切なし"))


if __name__ == "__main__":
    unittest.main()
