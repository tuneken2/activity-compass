import unittest

from activity_compass.ui import (
    DEFAULT_VIEW,
    TYPE_LABELS,
    format_list_date,
    format_priority,
    format_priority_color,
)


class UiFormattingTests(unittest.TestCase):
    def test_project_label_uses_project_terminology(self) -> None:
        self.assertEqual(TYPE_LABELS["project"], "プロジェクト")

    def test_projects_are_the_default_view(self) -> None:
        self.assertEqual(DEFAULT_VIEW, "projects")

    def test_item_without_dates_is_indefinite(self) -> None:
        self.assertEqual(format_list_date(None, "予定"), ("無期限", "締切なし"))

    def test_priority_is_displayed_as_japanese_label(self) -> None:
        self.assertEqual(format_priority(3), "高")
        self.assertEqual(format_priority("2"), "中")
        self.assertEqual(format_priority(1), "低")
        self.assertEqual(format_priority(0), "—")

    def test_priority_text_color_is_graded(self) -> None:
        self.assertEqual(format_priority_color(3), "#A84628")
        self.assertEqual(format_priority_color("2"), "#8A6815")
        self.assertEqual(format_priority_color(1), "#3C7160")
        self.assertEqual(format_priority_color(0), "#6E7773")


if __name__ == "__main__":
    unittest.main()
