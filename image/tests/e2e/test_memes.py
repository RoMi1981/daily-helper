"""E2E tests for the Memes module — upload, list, delete, next rotation."""

from pathlib import Path

from playwright.sync_api import Page, expect

# Minimal 1×1 red PNG — no network access needed
_PIXEL_PNG = bytes(
    [
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
        0x00, 0x00, 0x02, 0x00, 0x01, 0xE2, 0x21, 0xBC,
        0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
        0x44, 0xAE, 0x42, 0x60, 0x82,
    ]
)


def _upload_meme(page: Page, live_server: str, tmp_path: Path, filename: str = "meme.png") -> None:
    img = tmp_path / filename
    img.write_bytes(_PIXEL_PNG)
    page.goto(f"{live_server}/memes")
    page.set_input_files('input[name="file"]', str(img))
    page.locator('button[type="submit"]').first.click()
    page.wait_for_load_state("networkidle")


class TestMemeUpload:
    def test_page_loads(self, page: Page, live_server):
        page.goto(f"{live_server}/memes")
        page.wait_for_load_state("networkidle")
        expect(page.locator("h1")).to_be_visible()

    def test_upload_form_is_present(self, page: Page, live_server):
        page.goto(f"{live_server}/memes")
        page.wait_for_load_state("networkidle")
        expect(page.locator('input[name="file"]')).to_be_visible()

    def test_meme_appears_in_list_after_upload(self, page: Page, live_server, tmp_path):
        _upload_meme(page, live_server, tmp_path, "meme_upload_test.png")
        page.goto(f"{live_server}/memes")
        page.wait_for_load_state("networkidle")
        # At least one meme image card should be visible
        expect(page.locator('img[onclick*="openLightbox"]').first).to_be_visible()

    def test_success_flash_shown_after_upload(self, page: Page, live_server, tmp_path):
        img = tmp_path / "meme_flash.png"
        img.write_bytes(_PIXEL_PNG)
        page.goto(f"{live_server}/memes")
        page.set_input_files('input[name="file"]', str(img))
        page.locator('button[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")
        expect(page.locator(".alert-success")).to_be_visible()


class TestMemeDelete:
    def test_delete_meme(self, page: Page, live_server, tmp_path):
        _upload_meme(page, live_server, tmp_path, "meme_to_delete.png")
        page.goto(f"{live_server}/memes")
        page.wait_for_load_state("networkidle")

        # Count memes before delete
        meme_cards = page.locator('img[onclick*="openLightbox"]')
        count_before = meme_cards.count()
        assert count_before >= 1

        page.evaluate("window.confirm = () => true")
        page.locator('form[action*="/delete"] button[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")

        # One fewer meme after delete
        meme_cards_after = page.locator('img[onclick*="openLightbox"]')
        count_after = meme_cards_after.count()
        assert count_after == count_before - 1


class TestMemeNext:
    def test_next_button_is_present_when_meme_exists(self, page: Page, live_server, tmp_path):
        _upload_meme(page, live_server, tmp_path, "meme_next_test.png")
        page.goto(f"{live_server}/memes")
        page.wait_for_load_state("networkidle")
        # The "next meme" button uses hx-post=/memes/next
        next_btn = page.locator('button[hx-post="/memes/next"]')
        expect(next_btn).to_be_visible()

    def test_next_button_rotates_meme(self, page: Page, live_server, tmp_path):
        _upload_meme(page, live_server, tmp_path, "meme_rotate.png")
        page.goto(f"{live_server}/memes")
        page.wait_for_load_state("networkidle")

        widget = page.locator("#meme-widget")
        expect(widget).to_be_visible()
        src_before = widget.locator("img").first.get_attribute("src")

        page.locator('button[hx-post="/memes/next"]').click()
        page.wait_for_load_state("networkidle")

        # Widget is still present after HTMX swap
        expect(page.locator("#meme-widget")).to_be_visible()
