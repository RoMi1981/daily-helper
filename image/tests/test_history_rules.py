"""History path parsing.

An unmatched path is dropped from the history without any error, so the point
of these tests is that every module which writes to a repo stays matchable —
not just that the current rules work.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core.settings_store import DEFAULTS  # noqa: E402
from core.storage import _HISTORY_RULES, GitStorage  # noqa: E402

# One representative path per module, as written by that module's storage. The
# two nested layouts are additionally checked against the storage classes below
# — an appointments rule pointing at appointments/{id}.yaml passed every test
# for months while no appointment ever showed up in the history.
SAMPLE_PATHS = {
    "knowledge": "knowledge/devops/abc123.md",
    "tasks": "tasks/abc123.yaml",
    "notes": "notes/abc123.yaml",
    "links": "links/abc123.yaml",
    "snippets": "snippets/abc123.yaml",
    "vacations": "vacations/entries/abc123.yaml",
    "appointments": "appointments/entries/abc123.yaml",
    "runbooks": "runbooks/abc123.yaml",
    "mail_templates": "mail_templates/abc123.yaml",
    "ticket_templates": "ticket_templates/abc123.yaml",
    "motd": "motd/abc123.yaml",
    "potd": "potd/abc123.png",
    "memes": "memes/abc123.jpg",
    "eol": "eol/abc123.yaml",
    "rss": "rss/abc123.yaml",
}


@pytest.fixture
def storage():
    s = GitStorage.__new__(GitStorage)
    s.repo_id = "r1"
    return s


def _parse(storage, path, action="A"):
    with patch.object(GitStorage, "read_committed", return_value=None):
        return storage._parse_history_path(path, action)


def test_every_enabled_module_is_covered(storage):
    """A module in modules_enabled writes to the repo, so its commits must show
    up in the history. Adding a module without a rule fails here."""
    missing = [m for m in DEFAULTS["modules_enabled"] if m not in SAMPLE_PATHS]
    assert missing == [], f"no sample path for {missing} — extend SAMPLE_PATHS and add a history rule"

    for module, path in SAMPLE_PATHS.items():
        change = _parse(storage, path)
        assert change is not None, f"{path} is not recognised as history"
        assert change["module"] == module


@pytest.mark.parametrize("module,path", sorted(SAMPLE_PATHS.items()))
def test_change_carries_the_fields_the_template_reads(storage, module, path):
    change = _parse(storage, path)
    for field in ("action", "path", "module", "category", "slug", "repo_id", "title", "deleted", "url"):
        assert field in change
    assert change["slug"] == "abc123"
    assert change["title"], "an empty title renders as a blank row"
    assert change["url"].startswith("/")


def test_deleted_paths_are_marked_and_still_parse(storage):
    change = _parse(storage, "eol/abc123.yaml", action="D")
    assert change["deleted"] is True
    assert change["title"] == "abc123"  # no committed content left to read


def test_unknown_paths_are_skipped(storage):
    for path in ("README.md", ".gitignore", "knowledge/deep/nested/file.md", "tasks/x/y/z.yaml"):
        assert _parse(storage, path) is None


def test_rule_urls_only_use_the_id_placeholder(storage):
    """url.format(id=...) raises on any other placeholder, which would turn a
    history page into a 500."""
    for rule in _HISTORY_RULES:
        rule.url.format(id="x")


@pytest.mark.parametrize(
    "module,storage_path,attr",
    [
        ("vacations", "modules.vacations.storage.VacationStorage", "_entries_dir"),
        ("appointments", "modules.appointments.storage.AppointmentStorage", "_entries_dir"),
    ],
)
def test_nested_layouts_match_the_storage_class(tmp_path, module, storage_path, attr):
    """The sample path is only worth something if it is where the module writes."""
    import importlib
    from unittest.mock import MagicMock

    mod_name, cls_name = storage_path.rsplit(".", 1)
    cls = getattr(importlib.import_module(mod_name), cls_name)
    git = MagicMock()
    git.local_path = tmp_path
    real_dir = getattr(cls(git), attr).relative_to(tmp_path).as_posix()

    sample_dir = SAMPLE_PATHS[module].rsplit("/", 1)[0]
    assert sample_dir == real_dir


def test_legacy_flat_appointment_paths_still_resolve(storage):
    """Repos written before the entries/ layout still carry these commits; the
    history must not go blank for them."""
    change = _parse(storage, "appointments/abc123.yaml")
    assert change is not None
    assert change["module"] == "appointments"
