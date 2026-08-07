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

    def test_open_button_only_renders_when_a_link_url_is_set(self) -> None:
        self.assertIn(
            '(row.link_url ? \'<button class="action orange" onclick="openLink()">\' '
            '+ escapeHtml(row.link_service ? row.link_service + "で開く" : "作品ページを開く") '
            '+ \'</button>\' : \'\') +',
            self.html,
        )

    def test_open_link_hands_the_url_to_the_os_with_a_browser_fallback(self) -> None:
        self.assertIn("function openLink()", self.html)
        self.assertIn('new ActiveXObject("WScript.Shell")', self.html)
        self.assertIn("shell.Run(", self.html)
        self.assertIn('window.open(url, "_blank");', self.html)


if __name__ == "__main__":
    unittest.main()
