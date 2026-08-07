import unittest
from pathlib import Path


class ListCompleteButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (
            Path(__file__).resolve().parents[1] / "desktop.hta"
        ).read_text(encoding="utf-8")

    def test_date_column_is_followed_by_a_done_column(self) -> None:
        self.assertIn(
            '<div class="head-date">期限 / 予定</div><div class="head-done"></div>',
            self.html,
        )
        self.assertIn(".c-done {", self.html)

    def test_row_shows_a_complete_button_unless_excluded(self) -> None:
        self.assertIn(
            'var showComplete = !isProject && !isHistory && !isReview '
            '&& view !== "done" && view !== "archive" && view !== "anime_manga";',
            self.html,
        )

    def test_complete_button_click_does_not_also_select_the_row(self) -> None:
        self.assertIn(
            'onclick="event.stopPropagation(); confirmCompleteRow(\' + i + \')"',
            self.html,
        )

    def test_completing_a_row_asks_for_confirmation_first(self) -> None:
        self.assertIn("function confirmCompleteRow(index)", self.html)
        self.assertIn('を完了にしますか？', self.html)
        self.assertIn(
            'if (!confirm("「" + row.title + "」を完了にしますか？")) return;',
            self.html,
        )
        self.assertIn('{status:"done"}', self.html)


if __name__ == "__main__":
    unittest.main()
