"""Tests for sprint_helper — calculation, naming, capacity."""

import os
import sys
from datetime import date, timedelta

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

from modules.calendar.sprint_helper import (
    get_sprint_for_date,
    get_sprints_in_range,
    get_sprints_in_year,
    count_days_overlap,
    capacity_for_sprint,
)

# Anchor: Monday 2026-01-05 — sprint 0: 2026-01-05..2026-01-25
ANCHOR = date(2026, 1, 5)
PREFIX = "PFM Sprint"


# ── get_sprint_for_date ───────────────────────────────────────────────────────

def test_sprint_for_anchor_date():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    assert sp["index"] == 0
    assert sp["start"] == ANCHOR
    assert sp["end"] == date(2026, 1, 25)
    assert sp["name"] == "PFM Sprint 2026-01-25"
    assert sp["is_start"] is True


def test_sprint_for_mid_sprint_date():
    mid = ANCHOR + timedelta(days=10)
    sp = get_sprint_for_date(mid, ANCHOR)
    assert sp["index"] == 0
    assert sp["is_start"] is False


def test_sprint_for_second_sprint():
    d = ANCHOR + timedelta(days=21)
    sp = get_sprint_for_date(d, ANCHOR)
    assert sp["index"] == 1
    assert sp["start"] == date(2026, 1, 26)
    assert sp["end"] == date(2026, 2, 15)
    assert sp["name"] == "PFM Sprint 2026-02-15"
    assert sp["is_start"] is True


def test_sprint_for_last_day_of_sprint():
    last = ANCHOR + timedelta(days=20)
    sp = get_sprint_for_date(last, ANCHOR)
    assert sp["index"] == 0  # still sprint 0


def test_sprint_custom_prefix():
    sp = get_sprint_for_date(ANCHOR, ANCHOR, prefix="XYZ")
    assert sp["name"].startswith("XYZ ")


def test_sprint_duration_default_3_weeks():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    delta = (sp["end"] - sp["start"]).days + 1
    assert delta == 21  # 3 weeks × 7 days


def test_sprint_duration_configurable():
    sp2 = get_sprint_for_date(ANCHOR, ANCHOR, duration_weeks=2)
    assert (sp2["end"] - sp2["start"]).days + 1 == 14

    sp4 = get_sprint_for_date(ANCHOR, ANCHOR, duration_weeks=4)
    assert (sp4["end"] - sp4["start"]).days + 1 == 28


# ── get_sprints_in_range ──────────────────────────────────────────────────────

def test_sprints_in_range_single_sprint():
    sprints = get_sprints_in_range(ANCHOR, ANCHOR + timedelta(days=5), ANCHOR)
    assert len(sprints) == 1
    assert sprints[0]["index"] == 0


def test_sprints_in_range_two_sprints():
    # range spans the boundary between sprint 0 and sprint 1
    start = ANCHOR + timedelta(days=15)
    end = ANCHOR + timedelta(days=25)
    sprints = get_sprints_in_range(start, end, ANCHOR)
    assert len(sprints) == 2
    assert sprints[0]["index"] == 0
    assert sprints[1]["index"] == 1


def test_sprints_in_range_exact_sprint():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    sprints = get_sprints_in_range(sp["start"], sp["end"], ANCHOR)
    assert len(sprints) == 1


# ── get_sprints_in_year ───────────────────────────────────────────────────────

def test_sprints_in_year_count():
    sprints = get_sprints_in_year(2026, ANCHOR)
    # 365 days / 21 ≈ 17.4 → expect 17 or 18 sprints overlapping the year
    assert 15 <= len(sprints) <= 20


def test_sprints_in_year_sorted():
    sprints = get_sprints_in_year(2026, ANCHOR)
    for i in range(len(sprints) - 1):
        assert sprints[i]["start"] < sprints[i + 1]["start"]


def test_sprints_in_year_all_overlap_year():
    sprints = get_sprints_in_year(2026, ANCHOR)
    year_start = date(2026, 1, 1)
    year_end = date(2026, 12, 31)
    for sp in sprints:
        assert sp["end"] >= year_start
        assert sp["start"] <= year_end


# ── count_days_overlap ────────────────────────────────────────────────────────

def test_overlap_full_within_sprint():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    hols: set = set()
    # Mon 2026-01-05 to Fri 2026-01-09 = 5 work days
    n = count_days_overlap(sp["start"], sp["end"], "2026-01-05", "2026-01-09", "BY", hols)
    assert n == 5


def test_overlap_no_overlap():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    hols: set = set()
    n = count_days_overlap(sp["start"], sp["end"], "2025-12-01", "2025-12-31", "BY", hols)
    assert n == 0


def test_overlap_partial():
    # Sprint 0: 2026-01-05..2026-01-25, entry starts before sprint
    hols: set = set()
    n = count_days_overlap(ANCHOR, ANCHOR + timedelta(days=20), "2026-01-01", "2026-01-07", "BY", hols)
    # Only 2026-01-05 (Mon) to 2026-01-07 (Wed) = 3 work days
    assert n == 3


def test_overlap_excludes_holidays():
    # 2026-01-06 is Heilige Drei Könige in BY
    from modules.vacations.holidays_helper import get_holidays
    hols = get_holidays(2026, "BY")
    n = count_days_overlap(ANCHOR, ANCHOR + timedelta(days=2), "2026-01-05", "2026-01-07", "BY", hols)
    # Jan 5 (Mon, work), Jan 6 (Tue, holiday), Jan 7 (Wed, work) → 2
    assert n == 2


def test_overlap_invalid_dates():
    hols: set = set()
    n = count_days_overlap(ANCHOR, ANCHOR + timedelta(days=20), "bad", "date", "BY", hols)
    assert n == 0


# ── capacity_for_sprint ───────────────────────────────────────────────────────

def test_capacity_empty_sprint():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    result = capacity_for_sprint(sp, [], [], [], "BY")
    # Sprint 0: 2026-01-05..2026-01-25 (21 days)
    # Jan 6 = Heilige Drei Könige (BY holiday)
    assert result["total_work_days"] > 0
    assert result["vac_approved_days"] == 0
    assert result["vac_planned_days"] == 0
    assert result["appt_blocked_days"] == 0
    assert result["remaining_days"] == result["total_work_days"]


def test_capacity_with_vacation():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    vac = [{"start_date": "2026-01-12", "end_date": "2026-01-14", "status": "approved"}]
    result = capacity_for_sprint(sp, vac, [], [], "BY")
    assert result["vac_approved_days"] == 3
    assert result["remaining_days"] == result["total_work_days"] - 3


def test_capacity_planned_vacation_separate():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    vac = [
        {"start_date": "2026-01-12", "end_date": "2026-01-14", "status": "approved"},
        {"start_date": "2026-01-19", "end_date": "2026-01-21", "status": "planned"},
    ]
    result = capacity_for_sprint(sp, vac, [], [], "BY")
    assert result["vac_approved_days"] == 3
    assert result["vac_planned_days"] == 3
    assert result["remaining_days"] == result["total_work_days"] - 3
    assert result["remaining_after_planned"] == result["total_work_days"] - 6


def test_capacity_blocked_appointments_by_type():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    appts = [
        {"start_date": "2026-01-08", "end_date": "2026-01-09", "type": "training"},
        {"start_date": "2026-01-12", "end_date": "2026-01-12", "type": "other"},
    ]
    # Only training blocked
    result = capacity_for_sprint(sp, [], appts, ["training"], "BY")
    assert result["appt_blocked_days"] == 2

    # Nothing blocked
    result2 = capacity_for_sprint(sp, [], appts, [], "BY")
    assert result2["appt_blocked_days"] == 0


def test_capacity_pct_calculation():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    result = capacity_for_sprint(sp, [], [], [], "BY")
    # No blocks → remaining == total → 100%
    assert result["capacity_pct"] == 100


def test_capacity_pct_fully_blocked():
    sp = get_sprint_for_date(ANCHOR, ANCHOR)
    total = capacity_for_sprint(sp, [], [], [], "BY")["total_work_days"]
    # Approve vacation for entire sprint
    vac = [{"start_date": sp["start"].isoformat(), "end_date": sp["end"].isoformat(), "status": "approved"}]
    result = capacity_for_sprint(sp, vac, [], [], "BY")
    assert result["remaining_days"] <= 0
    assert result["capacity_pct"] == 0
