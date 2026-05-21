"""E2E tests for the Picture of the Day (PotD) module — upload, list, delete."""

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


def _upload_potd(page: Page, live_server: str, tmp_path: Path, filename: str = "potd.png") -> None:
    img = tmp_path / filename
    img.write_bytes(_PIXEL_PNG)
    page.goto(f"{live_server}/potd")
    page.set_input_files('input[name="file"]', str(img))
    page.locator('button[type="submit"]').first.click()
    page.wait_for_load_state("networkidle")


class TestPotdPage:
    def test_page_loads(self, page: Page, live_server):
        page.goto(f"{live_server}/potd")
        page.wait_for_load_state("networkidle")
        expect(page.locator("h1")).to_be_visible()

    def test_upload_form_is_present(self, page: Page, live_server):
        page.goto(f"{live_server}/potd")
        page.wait_for_load_state("networkidle")
        expect(page.locator('input[name="file"]')).to_be_visible()


class TestPotdUpload:
    def test_image_appears_after_upload(self, page: Page, live_server, tmp_path):
        _upload_potd(page, live_server, tmp_path, "potd_appears.png")
        page.goto(f"{live_server}/potd")
        page.wait_for_load_state("networkidle")
        # Image thumbnail should be visible in the collection
        expect(page.locator('[onclick*="openLightbox"]').first).to_be_visible()

    def test_success_flash_shown_after_upload(self, page: Page, live_server, tmp_path):
        img = tmp_path / "potd_flash.png"
        img.write_bytes(_PIXEL_PNG)
        page.goto(f"{live_server}/potd")
        page.set_input_files('input[name="file"]', str(img))
        page.locator('button[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")
        expect(page.locator(".alert-success")).to_be_visible()

    def test_thumbnail_visible_with_id(self, page: Page, live_server, tmp_path):
        _upload_potd(page, live_server, tmp_path, "potd_thumb.png")
        page.goto(f"{live_server}/potd")
        page.wait_for_load_state("networkidle")

        # Each entry shows a monospace ID label
        id_labels = page.locator(".card span[style*='monospace']")
        assert id_labels.count() >= 1


class TestPotdDelete:
    def test_delete_entry(self, page: Page, live_server, tmp_path):
        _upload_potd(page, live_server, tmp_path, "potd_delete.png")
        page.goto(f"{live_server}/potd")
        page.wait_for_load_state("networkidle")

        entries_before = page.locator('form[action*="/delete"]').count()
        assert entries_before >= 1

        page.evaluate("window.confirm = () => true")
        page.locator('form[action*="/delete"] button[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")

        entries_after = page.locator('form[action*="/delete"]').count()
        assert entries_after == entries_before - 1

    def test_delete_button_present_for_each_entry(self, page: Page, live_server, tmp_path):
        _upload_potd(page, live_server, tmp_path, "potd_btn_check.png")
        page.goto(f"{live_server}/potd")
        page.wait_for_load_state("networkidle")

        # Every entry should have a delete button
        delete_buttons = page.locator('form[action*="/delete"] button[type="submit"]')
        assert delete_buttons.count() >= 1
