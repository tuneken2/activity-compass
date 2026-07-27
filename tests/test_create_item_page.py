import unittest
from pathlib import Path


class CreateItemPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (
            Path(__file__).resolve().parents[1] / "desktop.hta"
        ).read_text(encoding="utf-8")

    def test_distinct_create_action_is_first_sidebar_button(self) -> None:
        sidebar = self.html[
            self.html.index('<aside class="sidebar">') : self.html.index("</aside>")
        ]
        create_position = sidebar.index('class="create-nav"')
        first_regular_nav_position = sidebar.index('class="nav active"')

        self.assertLess(create_position, first_regular_nav_position)
        self.assertIn("＋</span>新しく追加", sidebar)

    def test_old_quick_add_field_is_removed(self) -> None:
        self.assertNotIn('id="quickInput"', self.html)
        self.assertNotIn('function quickAdd()', self.html)
        self.assertNotIn('placeholder="新しいタスクを追加"', self.html)

    def test_create_page_collects_title_details_and_planning_fields(self) -> None:
        create_page = self.html[
            self.html.index('<section class="create-page"') :
            self.html.index("</section>", self.html.index('<section class="create-page"'))
        ]

        for field_id in (
            "createTitle",
            "createType",
            "createStatus",
            "createProject",
            "createDue",
            "createScheduled",
            "createEffort",
            "createPriority",
            "createDetails",
        ):
            self.assertIn(f'id="{field_id}"', create_page)

    def test_create_submission_uses_full_item_api(self) -> None:
        self.assertIn('request("POST", "/v1/items", payload', self.html)
        self.assertIn("details: document.getElementById(\"createDetails\").value", self.html)
        self.assertIn("changeView(targetView, item.id)", self.html)


if __name__ == "__main__":
    unittest.main()
