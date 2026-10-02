"""Tests for the Vacations ICS generator (previously untested — TIME-07)."""

import os
import sys
from datetime import date

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"

import main as _main_module  # noqa: F401  — ensures app package init runs like other test files

# ── _work_days ────────────────────────────────────────────────────────────


def test_work_days_excludes_weekend():
    from modules.vacations.ics_generator import _work_days

    # 2026-05-04 (Mon) .. 2026-05-10 (Sun) — a full week, no BY holidays in range
    days = _work_days("2026-05-04", "2026-05-10", "BY")
    assert days == [date(2026, 5, d) for d in range(4, 9)]  # Mon-Fri only


def test_work_days_excludes_public_holiday():
    from modules.vacations.ics_generator import _work_days

    # 2026-01-01 is New Year's Day (public holiday everywhere in Germany)
    days = _work_days("2025-12-30", "2026-01-02", "BY")
    assert date(2026, 1, 1) not in days


def test_work_days_inverted_range_returns_empty():
    from modules.vacations.ics_generator import _work_days

    assert _work_days("2026-05-10", "2026-05-04", "BY") == []


def test_work_days_invalid_date_returns_empty():
    from modules.vacations.ics_generator import _work_days

    assert _work_days("not-a-date", "2026-05-10", "BY") == []


# ── _escape_ics / CRLF injection (TIME-02) ──────────────────────────────────


def test_escape_ics_neutralizes_bare_cr():
    from modules.vacations.ics_generator import _escape_ics

    assert "\r" not in _escape_ics("line1\rline2")
    assert "\r" not in _escape_ics("line1\r\nline2")


def test_escape_ics_escapes_special_chars():
    from modules.vacations.ics_generator import _escape_ics

    assert _escape_ics("a;b,c\\d\ne") == "a\\;b\\,c\\\\d\\ne"


def test_generate_ics_note_with_crlf_does_not_inject_property():
    from modules.vacations.ics_generator import generate_ics

    entry = {
        "id": "vac-crlf",
        "start_date": "2026-05-04",
        "end_date": "2026-05-04",
        "note": "hello\r\nX-INJECTED:evil",
    }
    profile = {"show_as": "oof", "all_day": True, "body": "{note}"}
    ics = generate_ics(entry, profile, "BY")
    assert "X-INJECTED:evil" not in ics.split("\r\n")


# ── _fold ────────────────────────────────────────────────────────────────


def test_fold_short_line_untouched():
    from modules.vacations.ics_generator import _fold

    line = "SUMMARY:short"
    assert _fold(line) == line + "\r\n"


def test_fold_long_line_wraps_at_75_octets():
    from modules.vacations.ics_generator import _fold

    line = "SUMMARY:" + ("x" * 100)
    folded = _fold(line)
    physical_lines = folded.split("\r\n")[:-1]  # trailing empty from final \r\n
    assert len(physical_lines) > 1
    assert all(len(pl.encode("utf-8")) <= 75 for pl in physical_lines)
    # continuation lines are space-prefixed per RFC 5545
    assert physical_lines[1].startswith(" ")


# ── generate_ics ─────────────────────────────────────────────────────────


def test_generate_ics_basic():
    from modules.vacations.ics_generator import generate_ics

    entry = {"id": "vac-1", "start_date": "2026-05-04", "end_date": "2026-05-05", "note": "Beach"}
    profile = {"show_as": "oof", "all_day": True}
    ics = generate_ics(entry, profile, "BY")
    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics
    # One event spanning the whole range, not one per work day — a per-day
    # split would show the vacation as separate daily entries in Outlook.
    assert ics.count("BEGIN:VEVENT") == 1
    assert "DTSTART;VALUE=DATE:20260504" in ics
    assert "DTEND;VALUE=DATE:20260506" in ics
    assert "PRODID:-//Daily Helper//Vacation//EN" in ics


def test_generate_ics_all_day_spans_weekend_as_one_event():
    """A vacation crossing a weekend still produces a single all-day VEVENT
    covering the full range (weekends included), not one event per work day."""
    from modules.vacations.ics_generator import generate_ics

    entry = {"id": "vac-1b", "start_date": "2026-08-03", "end_date": "2026-08-11", "note": ""}
    profile = {"show_as": "oof", "all_day": True}
    ics = generate_ics(entry, profile, "BY")
    assert ics.count("BEGIN:VEVENT") == 1
    assert "DTSTART;VALUE=DATE:20260803" in ics
    assert "DTEND;VALUE=DATE:20260812" in ics


def test_generate_ics_all_day_dtend_is_exclusive():
    """DTEND for an all-day VEVENT must be the day *after* DTSTART (RFC 5545:
    DTEND is exclusive) — otherwise Outlook renders a one-day-too-long event."""
    from modules.vacations.ics_generator import generate_ics

    entry = {"id": "vac-2", "start_date": "2026-05-04", "end_date": "2026-05-04", "note": ""}
    profile = {"show_as": "oof", "all_day": True}
    ics = generate_ics(entry, profile, "BY")
    assert "DTSTART;VALUE=DATE:20260504" in ics
    assert "DTEND;VALUE=DATE:20260505" in ics


def test_generate_ics_timed_events_include_vtimezone():
    from modules.vacations.ics_generator import generate_ics

    entry = {"id": "vac-3", "start_date": "2026-05-04", "end_date": "2026-05-04", "note": ""}
    profile = {"show_as": "busy", "all_day": False, "start_time": "09:00", "end_time": "17:30"}
    ics = generate_ics(entry, profile, "BY")
    assert "BEGIN:VTIMEZONE" in ics
    assert "TZID:Europe/Berlin" in ics
    assert "DTSTART;TZID=Europe/Berlin:20260504T090000" in ics
    assert "DTEND;TZID=Europe/Berlin:20260504T173000" in ics


def test_generate_ics_empty_range_has_no_vevents():
    from modules.vacations.ics_generator import generate_ics

    entry = {"id": "vac-4", "start_date": "2026-05-10", "end_date": "2026-05-04", "note": ""}
    profile = {"show_as": "oof", "all_day": True}
    ics = generate_ics(entry, profile, "BY")
    assert "BEGIN:VEVENT" not in ics
    assert "BEGIN:VCALENDAR" in ics


def test_generate_ics_placeholders_resolved():
    from modules.vacations.ics_generator import generate_ics

    entry = {"id": "vac-5", "start_date": "2026-05-04", "end_date": "2026-05-05", "note": "Trip"}
    profile = {
        "show_as": "oof",
        "all_day": True,
        "subject": "OOO {start_date}-{end_date} ({days}d)",
        "body": "Note: {note}",
    }
    ics = generate_ics(entry, profile, "BY")
    assert "SUMMARY:OOO 2026-05-04-2026-05-05 (2d)" in ics
    assert "DESCRIPTION:Note: Trip" in ics


def test_generate_ics_no_online_meeting_suppresses_teams_link():
    from modules.vacations.ics_generator import generate_ics

    entry = {"id": "vac-6", "start_date": "2026-05-04", "end_date": "2026-05-04", "note": ""}
    profile = {"show_as": "oof", "all_day": True, "no_online_meeting": True}
    ics = generate_ics(entry, profile, "BY")
    assert "X-MICROSOFT-SKYPETEAMSMEETINGURL:" in ics
    assert "X-MICROSOFT-ONLINEMEETINGCONFLINK:" in ics


def test_generate_ics_recipients_required_and_optional():
    from modules.vacations.ics_generator import generate_ics

    entry = {"id": "vac-7", "start_date": "2026-05-04", "end_date": "2026-05-04", "note": ""}
    profile = {
        "show_as": "oof",
        "all_day": True,
        "recipients_required": ["boss@x.com"],
        "recipients_optional": ["team@x.com"],
    }
    ics = generate_ics(entry, profile, "BY")
    assert "ROLE=REQ-PARTICIPANT:mailto:boss@x.com" in ics
    assert "ROLE=OPT-PARTICIPANT:mailto:team@x.com" in ics


def test_generate_ics_legacy_recipients_field_fallback():
    from modules.vacations.ics_generator import generate_ics

    entry = {"id": "vac-8", "start_date": "2026-05-04", "end_date": "2026-05-04", "note": ""}
    profile = {"show_as": "oof", "all_day": True, "recipients": ["legacy@x.com"]}
    ics = generate_ics(entry, profile, "BY")
    assert "ROLE=REQ-PARTICIPANT:mailto:legacy@x.com" in ics


# ── generate_holiday_ics ─────────────────────────────────────────────────


def test_generate_holiday_ics_basic():
    from modules.vacations.ics_generator import generate_holiday_ics

    profile = {"show_as": "free", "subject": "{name}"}
    ics = generate_holiday_ics("Neujahr", "2026-01-01", profile)
    assert "BEGIN:VEVENT" in ics
    assert "SUMMARY:Neujahr" in ics
    assert "DTSTART;VALUE=DATE:20260101" in ics
    assert "DTEND;VALUE=DATE:20260102" in ics


def test_generate_holiday_ics_invalid_date_falls_back_to_today():
    from modules.vacations.ics_generator import generate_holiday_ics

    profile = {"show_as": "free"}
    ics = generate_holiday_ics("Bad Date Holiday", "not-a-date", profile)
    assert "BEGIN:VEVENT" in ics  # does not raise, still produces a valid event


# ── filenames ────────────────────────────────────────────────────────────


def test_profile_filename_with_entry_date_range():
    from modules.vacations.ics_generator import profile_filename

    profile = {"name": "Team Kalender"}
    entry = {"start_date": "2026-05-01", "end_date": "2026-05-10"}
    assert profile_filename(profile, entry) == "team-kalender_2026-05-01_2026-05-10.ics"


def test_profile_filename_without_entry():
    from modules.vacations.ics_generator import profile_filename

    assert profile_filename({"name": "My Profile"}) == "my-profile.ics"


def test_profile_filename_empty_name_defaults_to_export():
    from modules.vacations.ics_generator import profile_filename

    assert profile_filename({}) == "export.ics"


def test_holiday_profile_filename_basic():
    from modules.vacations.ics_generator import holiday_profile_filename

    profile = {"name": "Team Kalender"}
    fname = holiday_profile_filename(profile, "2026-01-01", "Neujahr")
    assert fname == "team-kalender_2026-01-01_neujahr.ics"
