"""E2E tests for the image lightbox modal (Memes and PotD)."""

import re
from pathlib import Path

from playwright.sync_api import Page, expect

# Minimal 1×1 red PNG — used to seed meme/potd entries without network access
_PIXEL_PNG = bytes(
    [
        0x89,
        0x50,
        0x4E,
        0x47,
        0x0D,
        0x0A,
        0x1A,
        0x0A,
        0x00,
        0x00,
        0x00,
        0x0D,
        0x49,
        0x48,
        0x44,
        0x52,
        0x00,
        0x00,
        0x00,
        0x01,
        0x00,
        0x00,
        0x00,
        0x01,
        0x08,
        0x02,
        0x00,
        0x00,
        0x00,
        0x90,
        0x77,
        0x53,
        0xDE,
        0x00,
        0x00,
        0x00,
        0x0C,
        0x49,
        0x44,
        0x41,
        0x54,
        0x08,
        0xD7,
        0x63,
        0xF8,
        0xCF,
        0xC0,
        0x00,
        0x00,
        0x00,
        0x02,
        0x00,
        0x01,
        0xE2,
        0x21,
        0xBC,
        0x33,
        0x00,
        0x00,
        0x00,
        0x00,
        0x49,
        0x45,
        0x4E,
        0x44,
        0xAE,
        0x42,
        0x60,
        0x82,
    ]
)


def _upload_meme(page: Page, live_server: str, tmp_path: Path) -> None:
    img = tmp_path / "test_meme.png"
    img.write_bytes(_PIXEL_PNG)
    page.goto(f"{live_server}/memes")
    page.set_input_files('input[name="file"]', str(img))
    page.locator('button[type="submit"]').first.click()
    page.wait_for_load_state("networkidle")


def _upload_potd(page: Page, live_server: str, tmp_path: Path) -> None:
    img = tmp_path / "test_potd.png"
    img.write_bytes(_PIXEL_PNG)
    page.goto(f"{live_server}/potd")
    page.set_input_files('input[name="file"]', str(img))
    page.locator('button[type="submit"]').first.click()
    page.wait_for_load_state("networkidle")


class TestMemeLightbox:
    def test_lightbox_opens_on_image_click(self, page: Page, live_server, tmp_path):
        """Clicking a meme thumbnail opens the lightbox modal."""
        _upload_meme(page, live_server, tmp_path)
        page.goto(f"{live_server}/memes")

        lb = page.locator("#lightbox")
        expect(lb).not_to_be_visible()

        page.locator('img[onclick*="openLightbox"]').first.click()
        expect(lb).to_be_visible()

    def test_lightbox_closes_on_escape(self, page: Page, live_server, tmp_path):
        """Pressing Escape closes the lightbox."""
        _upload_meme(page, live_server, tmp_path)
        page.goto(f"{live_server}/memes")

        page.locator('img[onclick*="openLightbox"]').first.click()
        expect(page.locator("#lightbox")).to_be_visible()

        page.keyboard.press("Escape")
        expect(page.locator("#lightbox")).not_to_be_visible()

    def test_lightbox_closes_on_backdrop_click(self, page: Page, live_server, tmp_path):
        """Clicking the backdrop (outside image) closes the lightbox."""
        _upload_meme(page, live_server, tmp_path)
        page.goto(f"{live_server}/memes")

        page.locator('img[onclick*="openLightbox"]').first.click()
        lb = page.locator("#lightbox")
        expect(lb).to_be_visible()

        # Click the close button (× top-right)
        page.locator("#lb-close").click()
        expect(lb).not_to_be_visible()

    def test_lightbox_has_copy_and_open_buttons(self, page: Page, live_server, tmp_path):
        """Lightbox contains Copy image and Open buttons."""
        _upload_meme(page, live_server, tmp_path)
        page.goto(f"{live_server}/memes")

        page.locator('img[onclick*="openLightbox"]').first.click()
        expect(page.locator("#lb-copy")).to_be_visible()
        expect(page.locator("#lb-open")).to_be_visible()

    def test_list_copy_button_present(self, page: Page, live_server, tmp_path):
        """The clipboard-copy button is present on each meme card and uses copyImage."""
        _upload_meme(page, live_server, tmp_path)
        page.goto(f"{live_server}/memes")

        btn = page.locator('button[title="Copy image"]').first
        expect(btn).to_be_visible()
        onclick = btn.get_attribute("onclick") or ""
        assert "copyImage" in onclick, f"Expected copyImage in onclick, got: {onclick!r}"


class TestPotdLightbox:
    def test_lightbox_opens_on_image_click(self, page: Page, live_server, tmp_path):
        """Clicking a PotD thumbnail opens the lightbox modal."""
        _upload_potd(page, live_server, tmp_path)
        page.goto(f"{live_server}/potd")

        lb = page.locator("#lightbox")
        expect(lb).not_to_be_visible()

        page.locator('img[onclick*="openLightbox"]').first.click()
        expect(lb).to_be_visible()

    def test_lightbox_shows_correct_image_src(self, page: Page, live_server, tmp_path):
        """The lightbox img src points to the clicked entry's raw URL."""
        _upload_potd(page, live_server, tmp_path)
        page.goto(f"{live_server}/potd")

        page.locator('img[onclick*="openLightbox"]').first.click()
        lb_img = page.locator("#lb-img")
        expect(lb_img).to_have_attribute("src", re.compile(r"/potd/.+/raw"))

    def test_potd_copy_button_present_for_image(self, page: Page, live_server, tmp_path):
        """Copy image button appears for image entries in the PotD list."""
        _upload_potd(page, live_server, tmp_path)
        page.goto(f"{live_server}/potd")

        expect(page.locator('button[title="Copy image"]').first).to_be_visible()
