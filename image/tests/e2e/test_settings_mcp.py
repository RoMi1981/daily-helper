"""E2E tests for Settings → MCP server: turn on, use the token, replace it, turn off."""

import re

from playwright.sync_api import Page, expect

MOBILE = {"width": 390, "height": 844}


def _tools_list(page: Page, live_server: str, token: str) -> int:
    resp = page.request.post(
        f"{live_server}/mcp",
        data='{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}',
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    return resp.status


def _section(page: Page):
    return page.locator("#mcp")


def test_turn_on_copy_command_replace_and_turn_off(page: Page, live_server: str) -> None:
    """The whole lifecycle as a user clicks it. The command is built in the
    browser from location.origin, so only a browser test sees the address and
    token it would hand to Claude Code. The command carries `-s user` so that one
    run makes the server available in every Claude Code session of the user, not
    only in the project where it was run (Robert, 2026-11-09)."""
    page.on("dialog", lambda d: d.accept())
    page.goto(f"{live_server}/settings#mcp")
    section = _section(page)
    if section.locator("#mcp-token").count():  # left on by an earlier run in this session
        section.get_by_role("button", name=re.compile("Turn off")).click()
        page.wait_for_load_state("networkidle")

    section.get_by_role("button", name=re.compile("Turn on")).click()
    page.wait_for_load_state("networkidle")
    token = section.locator("#mcp-token").input_value()
    assert len(token) >= 40
    command = section.locator("#mcp-command").input_value()
    assert command == (
        f"claude mcp add -s user --transport http daily-helper {live_server}/mcp "
        f'--header "Authorization: Bearer {token}"'
    )
    assert _tools_list(page, live_server, token) == 200

    section.get_by_role("button", name=re.compile("New token")).click()
    page.wait_for_load_state("networkidle")
    new_token = section.locator("#mcp-token").input_value()
    assert new_token != token
    assert _tools_list(page, live_server, token) == 401
    assert _tools_list(page, live_server, new_token) == 200

    section.get_by_role("button", name=re.compile("Turn off")).click()
    page.wait_for_load_state("networkidle")
    expect(section.locator("#mcp-token")).to_have_count(0)
    assert _tools_list(page, live_server, new_token) == 404


def test_cancelled_confirmation_keeps_the_token(page: Page, live_server: str) -> None:
    """Replacing the token cuts off connected clients, so it needs a confirmation."""
    page.goto(f"{live_server}/settings#mcp")
    section = _section(page)
    if not section.locator("#mcp-token").count():
        section.get_by_role("button", name=re.compile("Turn on")).click()
        page.wait_for_load_state("networkidle")
    token = section.locator("#mcp-token").input_value()
    page.once("dialog", lambda d: d.dismiss())
    section.get_by_role("button", name=re.compile("New token")).click()
    page.wait_for_timeout(500)
    assert section.locator("#mcp-token").input_value() == token
    page.on("dialog", lambda d: d.accept())
    section.get_by_role("button", name=re.compile("Turn off")).click()
    page.wait_for_load_state("networkidle")


def test_mcp_section_fits_a_phone(page: Page, live_server: str) -> None:
    """The token and the long command must wrap inside the card on a phone,
    not push the page wider than the screen."""
    page.set_viewport_size(MOBILE)
    page.on("dialog", lambda d: d.accept())
    page.goto(f"{live_server}/settings#mcp")
    section = _section(page)
    if not section.locator("#mcp-token").count():
        section.get_by_role("button", name=re.compile("Turn on")).click()
        page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth") <= MOBILE["width"]
    box = section.locator("#mcp-command").bounding_box()
    assert box and box["x"] + box["width"] <= MOBILE["width"]
    section.get_by_role("button", name=re.compile("Turn off")).click()
    page.wait_for_load_state("networkidle")
