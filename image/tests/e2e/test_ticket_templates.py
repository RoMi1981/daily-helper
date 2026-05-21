"""E2E tests for the Ticket Templates module — create, edit, delete."""

from playwright.sync_api import Page, expect


def _create_template(
    page: Page,
    base: str,
    name: str,
    description: str = "",
    body: str = "",
) -> None:
    page.goto(f"{base}/ticket-templates/new")
    page.fill('[name="name"]', name)
    if description:
        page.fill('[name="description"]', description)
    if body:
        page.fill('[name="body"]', body)
    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")


class TestTicketTemplateCreate:
    def test_page_loads(self, page: Page, live_server):
        page.goto(f"{live_server}/ticket-templates")
        page.wait_for_load_state("networkidle")
        expect(page.locator("h1")).to_be_visible()

    def test_new_form_has_required_fields(self, page: Page, live_server):
        page.goto(f"{live_server}/ticket-templates/new")
        page.wait_for_load_state("networkidle")
        expect(page.locator('[name="name"]')).to_be_visible()
        expect(page.locator('[name="description"]')).to_be_visible()
        expect(page.locator('[name="body"]')).to_be_visible()

    def test_template_appears_in_list_after_create(self, page: Page, live_server):
        _create_template(page, live_server, "E2E Template Alpha", description="Alpha description")
        page.goto(f"{live_server}/ticket-templates")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Template Alpha").first).to_be_visible()

    def test_template_description_visible_in_list(self, page: Page, live_server):
        _create_template(
            page, live_server, "E2E Template Beta", description="Beta short description"
        )
        page.goto(f"{live_server}/ticket-templates")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("Beta short description").first).to_be_visible()

    def test_template_with_body_shows_show_body_toggle(self, page: Page, live_server):
        _create_template(
            page,
            live_server,
            "E2E Template Gamma",
            body="Steps to reproduce:\n1. Do X\n2. Do Y",
        )
        page.goto(f"{live_server}/ticket-templates")
        page.wait_for_load_state("networkidle")
        card = page.locator(".mod-card", has_text="E2E Template Gamma").first
        expect(card.locator("summary")).to_be_visible()


class TestTicketTemplateEdit:
    def test_edit_form_is_prefilled(self, page: Page, live_server):
        _create_template(
            page, live_server, "E2E Template Delta", description="Delta original"
        )
        page.goto(f"{live_server}/ticket-templates")
        page.wait_for_load_state("networkidle")

        card = page.locator(".mod-card", has_text="E2E Template Delta").first
        card.locator('a[href*="/edit"]').click()
        page.wait_for_load_state("networkidle")

        expect(page.locator('[name="name"]')).to_have_value("E2E Template Delta")
        expect(page.locator('[name="description"]')).to_have_value("Delta original")

    def test_edit_updates_template_name(self, page: Page, live_server):
        _create_template(page, live_server, "E2E Template Epsilon")
        page.goto(f"{live_server}/ticket-templates")
        page.wait_for_load_state("networkidle")

        card = page.locator(".mod-card", has_text="E2E Template Epsilon").first
        card.locator('a[href*="/edit"]').click()
        page.wait_for_load_state("networkidle")

        page.fill('[name="name"]', "E2E Template Epsilon Renamed")
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        page.goto(f"{live_server}/ticket-templates")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Template Epsilon Renamed").first).to_be_visible()


class TestTicketTemplateDelete:
    def test_delete_removes_template(self, page: Page, live_server):
        _create_template(page, live_server, "E2E Template Zeta To Delete")
        page.goto(f"{live_server}/ticket-templates")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Template Zeta To Delete").first).to_be_visible()

        page.evaluate("window.confirm = () => true")
        card = page.locator(".mod-card", has_text="E2E Template Zeta To Delete").first
        card.locator('form[action*="/delete"] button[type="submit"]').click()
        page.wait_for_load_state("networkidle")

        expect(page.get_by_text("E2E Template Zeta To Delete")).not_to_be_visible()
