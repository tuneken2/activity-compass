import unittest
from pathlib import Path


class AnimeLinkButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (
            Path(__file__).resolve().parents[1] / "desktop.hta"
        ).read_text(encoding="utf-8")

    def test_link_fields_are_offered_for_anime_and_manga(self) -> None:
        self.assertIn('id="editLinkService" oninput="scheduleDetailAutoSave()"', self.html)
        self.assertIn('id="editLinkUrl" oninput="scheduleDetailAutoSave()"', self.html)

    def test_build_edit_payload_includes_link_fields_for_anime_and_manga(self) -> None:
        self.assertIn(
            'payload.link_service = document.getElementById("editLinkService").value;',
            self.html,
        )
        self.assertIn(
            'payload.link_url = document.getElementById("editLinkUrl").value;',
            self.html,
        )

    def test_detail_panel_has_no_open_link_button(self) -> None:
        # The open action lives in the list column (anime tab only), not the
        # detail panel, so the detail action-row must not duplicate it.
        self.assertNotIn('openLink()">', self.html)

    def test_list_column_only_offers_the_open_button_on_the_anime_tab(self) -> None:
        self.assertIn(
            'var showLink = view === "anime_manga" && !query && '
            '!isProject && !isHistory && !isReview;',
            self.html,
        )
        self.assertIn(
            '(showLink && row.link_url)\n          ? '
            '\'<div class="c-link"><button class="link-button" '
            'onclick="event.stopPropagation(); openLinkForRow(\' + i + \')">開く</button></div>\'',
            self.html,
        )

    def test_complete_button_is_hidden_on_the_anime_tab(self) -> None:
        self.assertIn(
            'var showComplete = !isProject && !isHistory && !isReview '
            '&& view !== "done" && view !== "archive" && view !== "anime_manga";',
            self.html,
        )

    def test_open_link_hands_the_url_to_the_os_with_a_browser_fallback(self) -> None:
        self.assertIn("function openLinkForRow(index)", self.html)
        self.assertIn('new ActiveXObject("WScript.Shell")', self.html)
        self.assertIn("shell.Run(", self.html)
        self.assertIn('window.open(url, "_blank");', self.html)


if __name__ == "__main__":
    unittest.main()
