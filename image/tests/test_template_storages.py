"""Tests for MailTemplateStorage and TicketTemplateStorage."""

import os
import sys

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self._committed = []

    def _pull(self): pass

    def _commit_and_push(self, msg):
        self._committed.append(msg)


@pytest.fixture()
def mail_storage(tmp_path):
    from modules.mail_templates.storage import MailTemplateStorage
    return MailTemplateStorage(FakeGit(tmp_path))


@pytest.fixture()
def ticket_storage(tmp_path):
    from modules.ticket_templates.storage import TicketTemplateStorage
    return TicketTemplateStorage(FakeGit(tmp_path))


# ── MailTemplateStorage ────────────────────────────────────────────────────

def test_mail_list_empty(mail_storage):
    assert mail_storage.list_templates() == []


def test_mail_create_and_list(mail_storage):
    t = mail_storage.create_template({
        "name": "Vacation Request",
        "to": "boss@company.com",
        "cc": "hr@company.com",
        "subject": "Vacation Request",
        "body": "Hi, I would like to request vacation.",
    })
    assert t["name"] == "Vacation Request"
    assert t["to"] == "boss@company.com"
    assert t["cc"] == "hr@company.com"
    assert "id" in t
    templates = mail_storage.list_templates()
    assert len(templates) == 1


def test_mail_get_template(mail_storage):
    t = mail_storage.create_template({"name": "Test", "subject": "Hello"})
    fetched = mail_storage.get_template(t["id"])
    assert fetched is not None
    assert fetched["name"] == "Test"


def test_mail_get_missing(mail_storage):
    assert mail_storage.get_template("doesnotexist") is None


def test_mail_update_template(mail_storage):
    t = mail_storage.create_template({"name": "Old", "subject": "Old subject"})
    updated = mail_storage.update_template(t["id"], {"name": "New", "subject": "New subject"})
    assert updated["name"] == "New"
    assert updated["subject"] == "New subject"


def test_mail_update_missing(mail_storage):
    assert mail_storage.update_template("ghost", {"name": "x"}) is None


def test_mail_delete_template(mail_storage):
    t = mail_storage.create_template({"name": "Bye"})
    assert mail_storage.delete_template(t["id"]) is True
    assert mail_storage.get_template(t["id"]) is None


def test_mail_delete_missing(mail_storage):
    assert mail_storage.delete_template("ghost") is False


def test_mail_sorted_by_name(mail_storage):
    mail_storage.create_template({"name": "Zebra"})
    mail_storage.create_template({"name": "Alpha"})
    mail_storage.create_template({"name": "Mango"})
    names = [t["name"] for t in mail_storage.list_templates()]
    assert names == sorted(names, key=str.lower)


def test_mail_commit_on_create(mail_storage):
    mail_storage.create_template({"name": "My Template"})
    assert any("add" in m and "My Template" in m for m in mail_storage._git._committed)


def test_mail_commit_on_update(mail_storage):
    t = mail_storage.create_template({"name": "T"})
    mail_storage._git._committed.clear()
    mail_storage.update_template(t["id"], {"name": "T updated"})
    assert any("update" in m for m in mail_storage._git._committed)


def test_mail_commit_on_delete(mail_storage):
    t = mail_storage.create_template({"name": "T"})
    mail_storage._git._committed.clear()
    mail_storage.delete_template(t["id"])
    assert any("delete" in m for m in mail_storage._git._committed)


def test_mail_strips_whitespace(mail_storage):
    t = mail_storage.create_template({"name": "  Spaced  ", "subject": "  Hello  "})
    assert t["name"] == "Spaced"
    assert t["subject"] == "Hello"


# ── TicketTemplateStorage ──────────────────────────────────────────────────

def test_ticket_list_empty(ticket_storage):
    assert ticket_storage.list_templates() == []


def test_ticket_create_and_list(ticket_storage):
    t = ticket_storage.create_template({
        "name": "Bug Report",
        "description": "Steps to reproduce",
        "body": "**Steps:**\n1. ...",
    })
    assert t["name"] == "Bug Report"
    assert t["description"] == "Steps to reproduce"
    assert "id" in t
    templates = ticket_storage.list_templates()
    assert len(templates) == 1


def test_ticket_get_template(ticket_storage):
    t = ticket_storage.create_template({"name": "Feature Request"})
    fetched = ticket_storage.get_template(t["id"])
    assert fetched is not None
    assert fetched["name"] == "Feature Request"


def test_ticket_get_missing(ticket_storage):
    assert ticket_storage.get_template("doesnotexist") is None


def test_ticket_update_template(ticket_storage):
    t = ticket_storage.create_template({"name": "Old", "description": "Old desc", "body": "Old body"})
    updated = ticket_storage.update_template(t["id"], {
        "name": "New",
        "description": "New desc",
        "body": "New body",
    })
    assert updated["name"] == "New"
    assert updated["description"] == "New desc"
    assert updated["body"] == "New body"


def test_ticket_update_missing(ticket_storage):
    assert ticket_storage.update_template("ghost", {"name": "x"}) is None


def test_ticket_delete_template(ticket_storage):
    t = ticket_storage.create_template({"name": "Bye"})
    assert ticket_storage.delete_template(t["id"]) is True
    assert ticket_storage.get_template(t["id"]) is None


def test_ticket_delete_missing(ticket_storage):
    assert ticket_storage.delete_template("ghost") is False


def test_ticket_sorted_by_name(ticket_storage):
    ticket_storage.create_template({"name": "Zebra"})
    ticket_storage.create_template({"name": "Alpha"})
    ticket_storage.create_template({"name": "Mango"})
    names = [t["name"] for t in ticket_storage.list_templates()]
    assert names == sorted(names, key=str.lower)


def test_ticket_commit_on_create(ticket_storage):
    ticket_storage.create_template({"name": "My Ticket Template"})
    assert any("add" in m and "My Ticket Template" in m for m in ticket_storage._git._committed)


def test_ticket_commit_on_update(ticket_storage):
    t = ticket_storage.create_template({"name": "T"})
    ticket_storage._git._committed.clear()
    ticket_storage.update_template(t["id"], {"name": "T updated"})
    assert any("update" in m for m in ticket_storage._git._committed)


def test_ticket_commit_on_delete(ticket_storage):
    t = ticket_storage.create_template({"name": "T"})
    ticket_storage._git._committed.clear()
    ticket_storage.delete_template(t["id"])
    assert any("delete" in m for m in ticket_storage._git._committed)


def test_ticket_strips_whitespace(ticket_storage):
    t = ticket_storage.create_template({"name": "  Padded  ", "description": "  desc  "})
    assert t["name"] == "Padded"
    assert t["description"] == "desc"
