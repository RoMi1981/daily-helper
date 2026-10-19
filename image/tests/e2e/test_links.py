"""E2E tests for the Links module — create, category filter, search."""

import re
import uuid

from playwright.sync_api import Page, expect


class TestLinkCreate:
    def test_link_appears_in_list(self, page: Page, live_server, seeded_links):
        """A seeded link appears on the links page."""
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Link Alpha").first).to_be_visible()

    def test_link_with_category_shows_category_filter(self, page: Page, live_server, seeded_links):
        """A link with a category makes that category filter appear."""
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E-Docs").first).to_be_visible()

    def test_link_url_is_rendered(self, page: Page, live_server, seeded_links):
        """The URL of the seeded link is shown (as href)."""
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")
        expect(page.locator('a[href="https://urlcheck.example.com"]').first).to_be_visible()


class TestLinkCategoryFilter:
    def test_category_filter_shows_only_matching_links(self, page: Page, live_server, seeded_links):
        """Clicking a category filter shows only links in that category."""
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")
        page.get_by_text("E2E-Filter").first.click()
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Filtered Link").first).to_be_visible()


class TestLinkSearch:
    def test_search_returns_matching_link(self, page: Page, live_server, seeded_links):
        """Search query filters the link list."""
        page.goto(f"{live_server}/links?q=Quasar")
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("E2E Quasar Link").first).to_be_visible()


class TestLinkBulkMove:
    def test_move_button_visible_with_multiple_sections(self, page: Page, live_server, seeded_links):
        """Bulk toolbar shows Move button when multiple sections exist."""
        import urllib.parse
        import urllib.request

        # Create a second section
        data = urllib.parse.urlencode({"name": "E2E Work Section"}).encode()
        req = urllib.request.Request(
            f"{live_server}/settings/link-sections/new",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError:
            pass

        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")

        # Enter bulk mode
        page.get_by_role("button", name="Select").first.click()
        page.wait_for_load_state("networkidle")

        # Check one link
        page.locator(".bulk-checkbox").first.check()

        # Move dropdown and button should appear
        expect(page.locator("select[name='target_section']")).to_be_visible()
        expect(page.get_by_role("button", name="Move").first).to_be_attached()


class TestLinkDeletePrompt:
    def test_title_cannot_break_out_of_the_delete_prompt(self, page: Page, live_server):
        """A link title is shown in the prompt verbatim and never executed.

        The prompt used to be `confirm('Delete \\'{{ link.title }}\\'?')` in an
        inline handler; the browser decodes &#39; before running it, so this
        title ran its own code on the delete click. Titles arrive from browser
        bookmarks via Floccus, i.e. from arbitrary web pages.
        """
        # Unique per run: the E2E data repo is shared across runs and the
        # dismissed prompt leaves the link in place until the cleanup below.
        tag = uuid.uuid4().hex[:6]
        title = f"E2E {tag} x'+(document.title='PWNED')+'"
        page.request.post(
            f"{live_server}/links/new",
            form={"title": title, "url": "https://example.com/e2e-xss", "category": "E2E"},
            max_redirects=0,
        )
        messages = []
        page.on("dialog", lambda d: (messages.append(d.message), d.dismiss()))
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")

        row = page.locator(".module-list-row", has_text=f"E2E {tag} x'")
        delete = row.locator("button.btn-danger")
        delete.click()
        page.wait_for_timeout(300)

        assert page.title() != "PWNED"
        assert messages and title in messages[0]
        expect(row).to_have_count(1)
        page.request.post(f"{live_server}{delete.get_attribute('formaction')}", max_redirects=0)


class TestLinkDelete:
    def test_every_row_delete_button_targets_its_own_entry(self, page: Page, live_server):
        """Each row's delete button posts to that row's own delete route.

        Same nested-form defect as in snippets and tasks: the row's own delete
        form sat inside the bulk form and was dropped by the parser.
        """
        tag = uuid.uuid4().hex[:6]
        for i in (1, 2):
            page.request.post(
                f"{live_server}/links/new",
                form={"title": f"E2E Row Target {tag} {i}", "url": f"https://example.com/{tag}/{i}", "category": ""},
                max_redirects=0,
            )
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")

        mismatches = page.evaluate("""() => [...document.querySelectorAll('.module-list-row')].map(row => {
            const id = row.querySelector('.bulk-checkbox').value;
            const btn = row.querySelector('button.btn-danger');
            return btn.formAction.endsWith('/links/' + id + '/delete') ? null : id + ' -> ' + btn.formAction;
        }).filter(Boolean)""")
        assert mismatches == []

        page.on("dialog", lambda d: d.accept())
        page.locator("#links-select-btn").click()
        for i in (1, 2):
            page.locator(".module-list-row", has_text=f"E2E Row Target {tag} {i}").locator(".bulk-checkbox").check()
        page.locator("#links-bulk-toolbar button.btn-danger").click()
        page.wait_for_load_state("networkidle")

        expect(page.locator(".module-list-row", has_text=f"E2E Row Target {tag}")).to_have_count(0)


class TestLinkFavourite:
    def test_star_toggles_for_a_title_with_double_quotes(self, page: Page, live_server):
        """The favourite star works when the title contains `"`.

        hx-vals was hand-written JSON with `| e`; the browser decoded the entity
        back into a bare quote, htmx could not parse the JSON and the click did
        nothing. The second click goes through the button the server sends back,
        which had the same defect.
        """
        tag = uuid.uuid4().hex[:6]
        title = f'E2E {tag} "quoted" title'
        page.request.post(
            f"{live_server}/links/new",
            form={"title": title, "url": f"https://example.com/fav-{tag}", "category": ""},
            max_redirects=0,
        )
        page.goto(f"{live_server}/links")
        page.wait_for_load_state("networkidle")
        row = page.locator(".module-list-row", has_text=f"E2E {tag}")

        row.locator(".fav-btn").click()
        expect(row.locator(".fav-btn")).to_have_class(re.compile(r"\bfav-active\b"))
        row.locator(".fav-btn").click()
        expect(row.locator(".fav-btn")).not_to_have_class(re.compile(r"\bfav-active\b"))

        page.request.post(
            f"{live_server}{row.locator('button.btn-danger').get_attribute('formaction')}", max_redirects=0
        )
