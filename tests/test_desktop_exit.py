import unittest
from pathlib import Path


class DesktopExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (
            Path(__file__).resolve().parents[1] / "desktop.hta"
        ).read_text(encoding="utf-8")

    def test_exit_button_is_immediately_after_refresh(self) -> None:
        refresh_position = self.html.index('id="refreshButton"')
        exit_position = self.html.index('class="exit-button"')
        header_end = self.html.index("</div>", exit_position)

        self.assertLess(refresh_position, exit_position)
        self.assertLess(exit_position, header_end)

    def test_exit_button_only_performs_complete_exit(self) -> None:
        self.assertIn(
            'onclick="exitApplication()" title="Activity Compassを完全に終了する">終了</button>',
            self.html,
        )
        self.assertIn("Activity Compassを完全に終了しますか？", self.html)
        self.assertNotIn("minimizeApplication", self.html)
        self.assertNotIn("window-menu", self.html)

    def test_sidebar_has_no_exit_button(self) -> None:
        sidebar = self.html[
            self.html.index('<aside class="sidebar">') : self.html.index("</aside>")
        ]
        self.assertNotIn("exitApplication", sidebar)


if __name__ == "__main__":
    unittest.main()
