"""Tests for the MCP server at /mcp: access control over HTTP and the tools in-process."""

import asyncio
import json
import os
import sys
from contextlib import ExitStack
from unittest.mock import patch

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"

import main as _main_module

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self.repo_id = "fake"
        self.committed = []

    def write_lock(self):
        if not hasattr(self, "_write_lock"):
            import threading

            self._write_lock = threading.RLock()
        return self._write_lock

    def _pull(self):
        pass

    def _commit_and_push(self, msg):
        self.committed.append(msg)

    def read_committed(self, path: str):
        try:
            with open(os.path.join(self.local_path, path), "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def list_committed(self, directory: str) -> list:
        full = os.path.join(self.local_path, directory)
        return os.listdir(full) if os.path.isdir(full) else []


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib

    from core import settings_store

    importlib.reload(settings_store)
    _main_module.settings_store = settings_store
    yield
    from core.state import reset_storage

    reset_storage()


@pytest.fixture()
def git(tmp_path):
    """One fake repo serving every module, wired into the MCP server."""
    repo = FakeGit(tmp_path / "repo")
    os.makedirs(repo.local_path)
    with ExitStack() as stack:
        stack.enter_context(patch("core.mcp_server.get_storage", return_value=object()))
        stack.enter_context(patch("core.mcp_server.get_module_stores", return_value=[repo]))
        stack.enter_context(patch("core.mcp_server.get_primary_store", return_value=repo))
        # calendar_month and sprint_capacity reuse the calendar router's loader.
        stack.enter_context(patch("modules.calendar.router.get_module_stores", return_value=[repo]))
        stack.enter_context(patch("modules.calendar.router.get_primary_store", return_value=repo))
        stack.enter_context(patch("modules.links.router.get_primary_store", return_value=repo))
        stack.enter_context(patch("modules.links.router.get_module_stores", return_value=[repo]))
        yield repo


def call(tool: str, args: dict | None = None):
    """Call a tool in-process; returns (is_error, structured result or error text)."""
    from core.mcp_server import server
    from mcp import Client

    async def run():
        async with Client(server) as c:
            return await c.call_tool(tool, args or {})

    res = asyncio.run(run())
    if res.is_error:
        return True, res.content[0].text
    return False, res.structured_content


def set_token(token: str) -> None:
    from core import settings_store

    cfg = settings_store.load()
    cfg["mcp_token"] = token
    settings_store.save(cfg)


# ── Access control over HTTP ──────────────────────────────────────────────────


def _tools_list(client, headers):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=headers)


def test_mcp_is_off_without_a_token():
    """The app has no login; an always-on endpoint would hand every visitor on
    the network read and write access, so it starts switched off."""
    from fastapi.testclient import TestClient

    with TestClient(_main_module.app) as client:
        resp = _tools_list(client, MCP_HEADERS)
    assert resp.status_code == 404


def test_mcp_rejects_missing_or_wrong_token():
    """The token is the only access control; the 401 carries WWW-Authenticate so clients
    know a bearer token is expected."""
    from fastapi.testclient import TestClient

    set_token("right-token")
    with TestClient(_main_module.app) as client:
        assert _tools_list(client, MCP_HEADERS).status_code == 401
        wrong = _tools_list(client, {**MCP_HEADERS, "Authorization": "Bearer wrong-token"})
    assert wrong.status_code == 401
    assert wrong.headers["www-authenticate"].startswith("Bearer")


def test_mcp_lists_tools_with_the_token_on_the_exact_path():
    """/mcp answers directly: a redirect to /mcp/ would point at http:// behind
    the TLS proxy, and clients need not follow redirects for POST."""
    from fastapi.testclient import TestClient

    set_token("right-token")
    with TestClient(_main_module.app) as client:
        resp = _tools_list(client, {**MCP_HEADERS, "Authorization": "Bearer right-token"})
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert {"search", "list_tasks", "get_note", "get_knowledge", "calendar_month"} <= names


def test_token_routes_turn_mcp_on_replace_and_off():
    """A replaced token must stop working at once (a leaked token is revoked by
    replacing it), and turning off must close /mcp again."""
    from core import settings_store
    from fastapi.testclient import TestClient

    with TestClient(_main_module.app) as client:
        client.post("/settings/mcp/token", follow_redirects=False)
        first = settings_store.load()["mcp_token"]
        client.post("/settings/mcp/token", follow_redirects=False)
        second = settings_store.load()["mcp_token"]
        assert len(first) >= 40 and second != first
        assert _tools_list(client, {**MCP_HEADERS, "Authorization": f"Bearer {first}"}).status_code == 401
        client.post("/settings/mcp/token/delete", follow_redirects=False)
        assert settings_store.load()["mcp_token"] == ""
        assert _tools_list(client, {**MCP_HEADERS, "Authorization": f"Bearer {second}"}).status_code == 404


def test_token_is_stored_encrypted():
    """settings.json may end up in a settings backup; the token must not be readable there."""
    from core import settings_store

    set_token("plain-token-value")
    raw = json.loads(settings_store.SETTINGS_PATH.read_text())
    assert raw["mcp_token"] and "plain-token-value" not in raw["mcp_token"]
    assert settings_store.load()["mcp_token"] == "plain-token-value"


def test_settings_page_shows_mcp_section():
    """Without the section a user cannot turn MCP on at all; with a token it must show
    the token and the off switch."""
    from fastapi.testclient import TestClient

    with TestClient(_main_module.app) as client:
        off = client.get("/settings").text
        set_token("visible-token")
        on = client.get("/settings").text
    assert 'id="mcp"' in off and 'action="/settings/mcp/token"' in off
    assert 'value="visible-token"' in on and "/settings/mcp/token/delete" in on


# ── Read tools ────────────────────────────────────────────────────────────────


def test_list_tasks_hides_done_unless_asked(git):
    """Done tasks would bury the open ones in a model's context; they come only on
    request."""
    from modules.tasks.storage import TaskStorage

    ts = TaskStorage(git)
    open_task = ts.create_task({"title": "Write report", "description": "quarterly"})
    done = ts.create_task({"title": "Old chore"})
    ts.toggle_done(done["id"])

    err, res = call("list_tasks")
    assert not err and [t["id"] for t in res["tasks"]] == [open_task["id"]]
    _, res = call("list_tasks", {"include_done": True})
    assert {t["id"] for t in res["tasks"]} == {open_task["id"], done["id"]}
    _, res = call("list_tasks", {"query": "QUARTERLY"})
    assert [t["title"] for t in res["tasks"]] == ["Write report"]


def test_get_task_and_unknown_id(git):
    """An unknown id must be an error, not an empty result a model could mistake for an
    empty task."""
    from modules.tasks.storage import TaskStorage

    task = TaskStorage(git).create_task({"title": "Call Bob"})
    assert call("get_task", {"task_id": task["id"]}) == (False, task)
    err, text = call("get_task", {"task_id": "nope"})
    assert err and "not found" in text


def test_disabled_module_is_refused(git):
    """A module switched off in Settings is hidden in the UI; MCP must not
    expose it either."""
    from core import settings_store

    cfg = settings_store.load()
    cfg["modules_enabled"]["tasks"] = False
    settings_store.save(cfg)
    err, text = call("list_tasks")
    assert err and "disabled" in text


def test_notes_list_omits_body_and_get_returns_it_decrypted(git):
    """Lists stay small (bodies can be long); get_note returns the readable text, as the
    web UI does."""
    from modules.notes.storage import NoteStorage

    note = NoteStorage(git).create_note({"subject": "Secret", "body": "the plain text", "encrypt": True})
    _, res = call("list_notes")
    assert [n["subject"] for n in res["notes"]] == ["Secret"]
    assert "body" not in res["notes"][0]
    _, full = call("get_note", {"note_id": note["id"]})
    assert full["body"] == "the plain text"


def test_runbook_list_and_get(git):
    """The list gives ids and titles only; the steps come from get_runbook."""
    from modules.runbooks.storage import RunbookStorage

    rb = RunbookStorage(git).create_runbook({"title": "Restore backup", "steps": [{"text": "stop app"}]})
    _, res = call("list_runbooks", {"query": "restore"})
    assert res["runbooks"] == [{"id": rb["id"], "title": "Restore backup", "description": rb.get("description", "")}]
    _, full = call("get_runbook", {"runbook_id": rb["id"]})
    assert full["steps"] == rb["steps"]


def test_list_templates_validates_kind(git):
    """An unknown kind must fail instead of silently listing one of the two template
    types."""
    err, text = call("list_templates", {"kind": "letter"})
    assert err and "mail" in text


def test_vacation_account_counts_entries(git):
    """The account must count work days of approved entries like the vacation page,
    without the bulky entry list."""
    from modules.vacations.storage import VacationStorage

    vs = VacationStorage(git)
    entry = vs.create_entry({"start_date": "2026-08-03", "end_date": "2026-08-07", "note": "summer"})
    vs.update_status(entry["id"], "approved")
    _, acc = call("vacation_account", {"year": 2026})
    assert acc["used_days"] == 5
    assert "entries" not in acc


def test_calendar_month_reports_holidays_vacation_and_tasks(git):
    """Only days that carry something are returned, so a model sees holidays, vacation
    and deadlines without 30 empty days."""
    from modules.tasks.storage import TaskStorage
    from modules.vacations.storage import VacationStorage

    VacationStorage(git).create_entry({"start_date": "2026-01-12", "end_date": "2026-01-12", "note": ""})
    TaskStorage(git).create_task({"title": "Tax return", "due_date": "2026-01-20"})
    _, res = call("calendar_month", {"year": 2026, "month": 1})
    days = {d["date"]: d for d in res["days"]}
    assert days["2026-01-01"]["holiday"] == "Neujahr"
    assert days["2026-01-12"]["vacation"] == "pending"
    assert days["2026-01-20"]["tasks_due"] == ["Tax return"]
    assert all(any(v for k, v in d.items() if k != "date") for d in res["days"])
    err, _ = call("calendar_month", {"year": 2026, "month": 13})
    assert err


def test_sprint_capacity_needs_anchor(git):
    """Without an anchor date there are no sprints; the tool must say so instead of
    returning an empty list."""
    err, text = call("sprint_capacity", {"year": 2026})
    assert err and "anchor" in text


# ── Write tools ───────────────────────────────────────────────────────────────


def test_there_is_no_delete_tool_and_write_tools_are_marked():
    """Deleting stays in the web UI on purpose; an MCP client must not be able
    to remove data. Write tools carry read_only_hint=False for the client."""
    from core.mcp_server import server

    async def run():
        return await server.list_tools()

    tools = {t.name: t for t in asyncio.run(run())}
    assert not [n for n in tools if "delete" in n or "remove" in n]
    assert tools["create_task"].annotations.read_only_hint is False
    assert tools["list_tasks"].annotations.read_only_hint is True


def test_create_task_commits_to_the_primary_repo(git):
    """A write lands in the module's primary repository as one commit, like a save in
    the web UI."""
    err, task = call("create_task", {"title": "Book flight", "due_date": "2026-12-01", "priority": "high"})
    assert not err and task["priority"] == "high" and task["due_date"] == "2026-12-01"
    assert git.committed == ["tasks: add 'Book flight'"]


@pytest.mark.parametrize(
    "args, message",
    [
        ({"title": "  "}, "title"),
        ({"title": "X", "due_date": "01.12.2026"}, "YYYY-MM-DD"),
        ({"title": "X", "priority": "urgent"}, "priority"),
    ],
)
def test_create_task_rejects_bad_input_without_committing(git, args, message):
    """The web form never sends these; a model might. Nothing may be written."""
    err, text = call("create_task", args)
    assert err and message in text
    assert git.committed == []


def test_update_task_changes_only_given_fields(git):
    """A model usually sends only the field it wants to change; the rest must survive,
    and an empty due date clears it."""
    from modules.tasks.storage import TaskStorage

    task = TaskStorage(git).create_task({"title": "Plan", "description": "keep me", "due_date": "2026-12-01"})
    _, updated = call("update_task", {"task_id": task["id"], "priority": "low"})
    assert updated["priority"] == "low"
    assert updated["description"] == "keep me" and updated["due_date"] == "2026-12-01"
    _, cleared = call("update_task", {"task_id": task["id"], "due_date": ""})
    assert cleared["due_date"] == ""


def test_complete_task_is_not_a_toggle(git):
    """toggle_done would reopen a task that is already done; completing twice
    must leave it done and add no commit."""
    from modules.tasks.storage import TaskStorage

    task = TaskStorage(git).create_task({"title": "Pay rent", "due_date": "2026-12-01", "recurring": "monthly"})
    git.committed.clear()
    _, done = call("complete_task", {"task_id": task["id"]})
    assert done["done"] is True
    commits = list(git.committed)
    _, again = call("complete_task", {"task_id": task["id"]})
    assert again["done"] is True and git.committed == commits
    _, open_tasks = call("list_tasks")
    assert [t["due_date"] for t in open_tasks["tasks"]] == ["2027-01-01"]


def test_update_note_keeps_an_encrypted_note_encrypted(git):
    """The storage removes encryption unless told to keep it; a tool that only
    passes the new body would write the note to the repo in plain text."""
    from modules.notes.storage import NoteStorage

    ns = NoteStorage(git)
    note = ns.create_note({"subject": "PIN", "body": "1234", "encrypt": True})
    err, _ = call("update_note", {"note_id": note["id"], "body": "5678"})
    assert not err
    raw = git.read_committed(f"notes/{note['id']}.md") or git.read_committed(f"notes/{note['id']}.yaml")
    assert raw is not None and b"5678" not in raw
    assert ns.get_note(note["id"])["body"] == "5678"


class FakeKnowledge:
    """Stands in for the multi-repo storage behind get_storage()."""

    def __init__(self):
        self.entries = {}

    def save_entry(self, repo_id, category, title, content):
        slug = title.lower().replace(" ", "-")
        self.entries[(repo_id, category, slug)] = {"title": title, "content": content}
        return {"repo_id": repo_id, "category": category, "slug": slug, "title": title}

    def get_entry(self, repo_id, category, slug):
        e = self.entries.get((repo_id, category, slug))
        return dict(e, repo_id=repo_id, category=category, slug=slug) if e else None

    def update_entry(self, repo_id, category, slug, title, content):
        self.entries[(repo_id, category, slug)] = {"title": title, "content": content}
        return {"repo_id": repo_id, "category": category, "slug": slug, "title": title}


@pytest.fixture()
def knowledge(git):
    from core import settings_store

    settings_store.upsert_repo({"id": "fake", "name": "Fake", "url": "x", "permissions": {"read": True, "write": True}})
    settings_store.upsert_repo({"id": "ro", "name": "RO", "url": "y", "permissions": {"read": True, "write": False}})
    kb = FakeKnowledge()
    with patch("core.mcp_server.get_storage", return_value=kb):
        yield kb


def test_create_knowledge_in_primary_repo_and_update_keeps_content(knowledge):
    """Without repo_id the entry goes to the knowledge module's primary repository; a
    title-only update keeps the content."""
    err, entry = call("create_knowledge", {"category": "linux", "title": "Disk usage", "content": "du -sh"})
    assert not err
    assert entry == {
        "repo_id": "fake",
        "category": "linux",
        "slug": "disk-usage",
        "title": "Disk usage",
        "pushed": True,
    }
    _, _ = call("update_knowledge", {"repo_id": "fake", "category": "linux", "slug": "disk-usage", "title": "Du"})
    assert knowledge.entries[("fake", "linux", "disk-usage")] == {"title": "Du", "content": "du -sh"}


def test_knowledge_writes_refuse_read_only_repos_and_slashes(knowledge):
    """The web route checks write permission only on update; the tool checks on create
    too. A slash would create a nested category path."""
    err, text = call("create_knowledge", {"category": "a", "title": "T", "content": "C", "repo_id": "ro"})
    assert err and "read-only" in text
    err, text = call("create_knowledge", {"category": "a/b", "title": "T", "content": "C"})
    assert err and "/" in text
    assert knowledge.entries == {}


def test_save_link_validates_scheme_and_section(git):
    """javascript: URLs are refused as in the web form; an unknown section must fail
    instead of _resolve_section silently filing the link in the first one."""
    err, link = call("save_link", {"title": "Docs", "url": "https://example.org"})
    assert not err and link["section"] == "default"
    err, text = call("save_link", {"title": "Bad", "url": "javascript:alert(1)"})
    assert err and "not allowed" in text
    err, text = call("save_link", {"title": "Lost", "url": "https://x.org", "section": "nope"})
    assert err and "not found" in text
    _, links = call("list_links")
    assert [x["title"] for x in links["links"]] == ["Docs"]


def test_create_snippet_drops_steps_without_command(git):
    """Like the web form: a step without a command is dropped, not saved empty."""
    _, sn = call(
        "create_snippet",
        {"title": "Logs", "steps": [{"description": "tail", "command": "tail -f x"}, {"description": "empty"}]},
    )
    assert sn["steps"] == [{"description": "tail", "command": "tail -f x"}]


def test_vacation_create_and_status(git):
    """The end may not precede the start, only known statuses are accepted, and approved
    days count as used."""
    err, text = call("create_vacation", {"start_date": "2026-08-07", "end_date": "2026-08-03"})
    assert err and "after" in text
    _, entry = call("create_vacation", {"start_date": "2026-08-03", "end_date": "2026-08-07", "note": "summer"})
    err, text = call("set_vacation_status", {"entry_id": entry["id"], "status": "maybe"})
    assert err
    _, approved = call("set_vacation_status", {"entry_id": entry["id"], "status": "approved"})
    assert approved["status"] == "approved"
    _, acc = call("vacation_account", {"year": 2026})
    assert acc["used_days"] == 5


def test_create_appointment_validates_type_and_dates(git):
    """Only the appointment types the calendar knows are accepted; the created entry is
    listed."""
    err, _ = call(
        "create_appointment", {"title": "X", "start_date": "2026-09-01", "end_date": "2026-09-01", "type": "party"}
    )
    assert err
    _, appt = call(
        "create_appointment",
        {"title": "Conf", "start_date": "2026-09-01", "end_date": "2026-09-02", "type": "conference"},
    )
    _, res = call("list_appointments", {"year": 2026})
    assert [a["id"] for a in res["appointments"]] == [appt["id"]]


# ── Findings of the error hunt ────────────────────────────────────────────────


def test_update_note_subject_only_keeps_encrypted_body_readable(git):
    """Without a body the storage read the stored ciphertext and encrypted it a
    second time; the note then showed 'enc:...' in the web UI for good."""
    from modules.notes.storage import NoteStorage

    ns = NoteStorage(git)
    note = ns.create_note({"subject": "PIN", "body": "1234", "encrypt": True})
    err, res = call("update_note", {"note_id": note["id"], "subject": "PIN new"})
    assert not err and res["subject"] == "PIN new" and res["encrypted"] is True
    assert ns.get_note(note["id"])["body"] == "1234"


def _break_vacations(git):
    path = os.path.join(git.local_path, "vacations", "entries")
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "broken.yaml"), "w") as f:
        f.write("start_date: [unclosed\n")


def test_calendar_and_capacity_fail_loudly_on_unreadable_vacations(git):
    """The calendar page's loader logs and returns no vacations; capacity would
    then report every sprint fully staffed."""
    from core import settings_store

    cfg = settings_store.load()
    cfg["sprint_anchor_date"] = "2026-01-05"
    settings_store.save(cfg)
    _break_vacations(git)
    for tool, args in (("calendar_month", {"year": 2026, "month": 11}), ("sprint_capacity", {"year": 2026})):
        err, text = call(tool, args)
        assert err and "Could not read vacations" in text, (tool, text)


def test_invalid_sprint_anchor_is_named(git):
    """An unparsable anchor used to read as 'no anchor set', which sends the user
    looking for a missing setting."""
    from core import settings_store

    cfg = settings_store.load()
    cfg["sprint_anchor_date"] = "05.01.2026"
    settings_store.save(cfg)
    err, text = call("sprint_capacity", {"year": 2026})
    assert err and "not a valid date" in text


def test_write_result_reports_repo_and_push_state(git):
    """After a network error the commit stays local (pending push); the web UI
    shows a banner, an MCP client must learn it from the result."""
    _, ok = call("create_task", {"title": "Pushed"})
    assert ok["pushed"] is True and ok["repo_id"] == "fake"
    git.has_pending_push = True
    _, local = call("create_task", {"title": "Only local"})
    assert local["pushed"] is False


def test_storage_error_reaches_the_client_with_its_cause(git):
    """Otherwise the client sees only 'Error executing tool' and cannot tell a rejected
    push from a bug."""
    from core.storage import GitStorageError

    def fail(msg):
        raise GitStorageError("Push rejected: remote has newer commits")

    git._commit_and_push = fail
    err, text = call("create_task", {"title": "X"})
    assert err and "Push rejected" in text


# ── Gaps found by the counter-check ───────────────────────────────────────────

WRITE_TOOLS = {
    "create_task",
    "update_task",
    "complete_task",
    "create_note",
    "update_note",
    "create_knowledge",
    "update_knowledge",
    "save_link",
    "create_snippet",
    "create_vacation",
    "set_vacation_status",
    "create_appointment",
}


def test_exactly_the_known_tools_can_write():
    """A new writing tool, whatever its name, must be added here on purpose,
    and must be marked as writing for the client."""
    from core.mcp_server import server

    tools = asyncio.run(server.list_tools())
    writing = {t.name for t in tools if t.annotations.read_only_hint is False}
    assert writing == WRITE_TOOLS
    assert all(t.annotations.read_only_hint is True for t in tools if t.name not in WRITE_TOOLS)


@pytest.mark.parametrize("header", ["right-token", "Bearer right-token-x", "bearer right-token", "Bearer  right-token"])
def test_token_must_match_exactly(header):
    """A substring or case-insensitive comparison would accept tokens that were never
    issued."""
    from fastapi.testclient import TestClient

    set_token("right-token")
    with TestClient(_main_module.app) as client:
        assert _tools_list(client, {**MCP_HEADERS, "Authorization": header}).status_code == 401


def test_mcp_works_after_a_restart():
    """A session manager runs only once; after a stop the next start needs a new
    one, or every request after an app restart fails."""
    from fastapi.testclient import TestClient

    set_token("right-token")
    headers = {**MCP_HEADERS, "Authorization": "Bearer right-token"}
    for _ in range(2):
        with TestClient(_main_module.app) as client:
            assert _tools_list(client, headers).status_code == 200


def test_create_note_encrypted_never_reaches_the_repo_in_plain_text(git):
    """encrypt is the user's choice to keep the text out of the git history; the repo
    file must hold ciphertext only."""
    _, note = call("create_note", {"subject": "Bank", "body": "geheim-123", "encrypt": True})
    raw = git.read_committed(f"notes/{note['id']}.yaml")
    assert raw is not None and b"geheim-123" not in raw
    assert "body" not in note


def test_update_note_keeps_a_plain_note_plain(git):
    """Preserving encryption must not turn on encryption for notes that never had it."""
    from modules.notes.storage import NoteStorage

    ns = NoteStorage(git)
    note = ns.create_note({"subject": "Shopping", "body": "milk"})
    call("update_note", {"note_id": note["id"], "body": "milk, eggs"})
    raw = git.read_committed(f"notes/{note['id']}.yaml")
    assert b"milk, eggs" in raw and not ns.get_note(note["id"]).get("encrypted")


@pytest.mark.parametrize(
    "module, tool, args",
    [
        ("links", "list_links", {}),
        ("links", "save_link", {"title": "T", "url": "https://x.org"}),
        ("knowledge", "list_knowledge", {}),
        ("knowledge", "create_knowledge", {"category": "c", "title": "T", "content": "C"}),
    ],
)
def test_modules_with_own_checks_refuse_when_disabled(git, module, tool, args):
    """Links and knowledge check the module switch themselves instead of through
    _stores; a switched-off module must stay hidden there too."""
    from core import settings_store

    cfg = settings_store.load()
    cfg["modules_enabled"][module] = False
    settings_store.save(cfg)
    err, text = call(tool, args)
    assert err and "disabled" in text


def test_knowledge_unknown_repo_blank_content_and_unknown_slug(knowledge):
    """An unknown repo counts as not writable, empty content is refused, and an unknown
    slug must not create an empty entry."""
    err, text = call("create_knowledge", {"category": "c", "title": "T", "content": "C", "repo_id": "nope"})
    assert err and "unknown" in text
    call("create_knowledge", {"category": "c", "title": "Keep", "content": "original"})
    err, _ = call("update_knowledge", {"repo_id": "fake", "category": "c", "slug": "keep", "content": "  "})
    assert err
    err, text = call("update_knowledge", {"repo_id": "fake", "category": "c", "slug": "missing", "title": "X"})
    assert err and "not found" in text
    assert knowledge.entries == {("fake", "c", "keep"): {"title": "Keep", "content": "original"}}


def test_more_input_validation_writes_nothing(git):
    """A model can send what the web form never sends; every refused call must leave the
    repository untouched."""
    from modules.tasks.storage import TaskStorage

    task = TaskStorage(git).create_task({"title": "Keep title"})
    git.committed.clear()
    cases = [
        ("update_task", {"task_id": task["id"], "title": "  "}, "title"),
        ("create_vacation", {"start_date": "", "end_date": ""}, "YYYY-MM-DD"),
        ("create_appointment", {"title": "X", "start_date": "01.09.2026", "end_date": "2026-09-02"}, "YYYY-MM-DD"),
        ("create_appointment", {"title": "X", "start_date": "2026-09-03", "end_date": "2026-09-02"}, "after"),
        ("set_vacation_status", {"entry_id": "nope", "status": "approved"}, "not found"),
        ("calendar_month", {"year": 2026, "month": 13}, "1-12"),
    ]
    for tool, args, message in cases:
        err, text = call(tool, args)
        assert err and message in text, (tool, text)
    assert git.committed == []


def test_calendar_month_shows_appointments_and_sprint_start_but_not_done_tasks(git):
    """Finished tasks are not deadlines any more; appointments and sprint starts belong
    on their day."""
    from core import settings_store
    from modules.appointments.storage import AppointmentStorage
    from modules.tasks.storage import TaskStorage

    cfg = settings_store.load()
    cfg["sprint_anchor_date"] = "2026-01-05"
    cfg["sprint_name_prefix"] = "S"
    settings_store.save(cfg)
    AppointmentStorage(git).create_entry({"title": "Workshop", "start_date": "2026-01-15", "end_date": "2026-01-15"})
    ts = TaskStorage(git)
    done = ts.create_task({"title": "Done already", "due_date": "2026-01-21"})
    ts.toggle_done(done["id"])
    _, res = call("calendar_month", {"year": 2026, "month": 1})
    days = {d["date"]: d for d in res["days"]}
    assert days["2026-01-15"]["appointments"] == ["Workshop"]
    assert "2026-01-21" not in days
    assert days["2026-01-05"]["sprint_start"].startswith("S")


def test_sprint_capacity_counts_vacation_across_the_year_boundary_and_blocked_appointments(git):
    """A sprint starting in December reaches into January, so the neighbouring years
    must be loaded; blocked appointment types reduce capacity."""
    from core import settings_store
    from modules.appointments.storage import AppointmentStorage
    from modules.vacations.storage import VacationStorage

    cfg = settings_store.load()
    cfg.update({"sprint_anchor_date": "2025-12-29", "sprint_duration_weeks": 3})
    cfg["sprint_blocked_appointment_types"] = ["training"]
    settings_store.save(cfg)
    vs = VacationStorage(git)
    vac = vs.create_entry({"start_date": "2025-12-29", "end_date": "2026-01-02"})
    vs.update_status(vac["id"], "approved")
    AppointmentStorage(git).create_entry(
        {"title": "Course", "start_date": "2026-01-07", "end_date": "2026-01-07", "type": "training"}
    )
    _, res = call("sprint_capacity", {"year": 2026})
    first = next(sp for sp in res["sprints"] if sp["start"] <= "2026-01-02" <= sp["end"])
    assert first["vac_approved_days"] >= 3
    assert first["appt_blocked_days"] == 1


def test_search_strips_highlight_markup(git):
    """The global search highlights with <mark> for the web page; a model should get
    plain text."""
    from modules.tasks.storage import TaskStorage

    TaskStorage(git).create_task({"title": "Renew passport", "description": "passport office"})
    with patch("core.global_search.get_primary_store", return_value=git):
        _, res = call("search", {"query": "passport"})
    snippets = [r["snippet"] for g in res["groups"] for r in g["results"]]
    assert snippets and all("<" not in s for s in snippets)


def test_list_templates_by_kind_and_query(git):
    """mail and ticket templates live in different modules and must not mix; the query
    filters within one kind."""
    from modules.mail_templates.storage import MailTemplateStorage
    from modules.ticket_templates.storage import TicketTemplateStorage

    MailTemplateStorage(git).create_template({"name": "Out of office", "subject": "Away", "body": "back soon"})
    TicketTemplateStorage(git).create_template({"name": "Bug report", "title": "Bug", "body": "steps"})
    _, mail = call("list_templates", {"kind": "mail"})
    assert [t["name"] for t in mail["templates"]] == ["Out of office"]
    _, ticket = call("list_templates", {"kind": "ticket", "query": "bug"})
    assert [t["name"] for t in ticket["templates"]] == ["Bug report"]
    _, none = call("list_templates", {"kind": "ticket", "query": "away"})
    assert none["templates"] == []
