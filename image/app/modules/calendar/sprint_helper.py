"""Sprint calculation helpers for configurable-length sprints."""

from datetime import date, timedelta

SPRINT_DAYS = 21  # default (3 weeks), overridden by sprint_duration_weeks setting


def _sprint_days(duration_weeks: int) -> int:
    return max(1, duration_weeks) * 7


def _sprint_index(d: date, anchor: date, sprint_days: int = SPRINT_DAYS) -> int:
    """0-based sprint index for a given date relative to anchor."""
    return (d - anchor).days // sprint_days


def get_sprint_for_date(d: date, anchor: date, prefix: str = "PFM Sprint",
                        duration_weeks: int = 3) -> dict:
    """Return sprint metadata for a given date."""
    days = _sprint_days(duration_weeks)
    idx = _sprint_index(d, anchor, days)
    start = anchor + timedelta(days=idx * days)
    end = start + timedelta(days=days - 1)
    return {
        "index": idx,
        "start": start,
        "end": end,
        "name": f"{prefix} {end.isoformat()}",
        "is_start": d == start,
    }


def get_sprints_in_range(range_start: date, range_end: date,
                         anchor: date, prefix: str = "PFM Sprint",
                         duration_weeks: int = 3) -> list[dict]:
    """All sprints overlapping [range_start, range_end], sorted by start."""
    sprints: list[dict] = []
    seen: set[int] = set()
    d = range_start
    while d <= range_end:
        sprint = get_sprint_for_date(d, anchor, prefix, duration_weeks)
        if sprint["index"] not in seen:
            seen.add(sprint["index"])
            sprints.append(sprint)
        d = sprint["end"] + timedelta(days=1)
    return sprints


def get_sprints_in_year(year: int, anchor: date,
                        prefix: str = "PFM Sprint",
                        duration_weeks: int = 3) -> list[dict]:
    return get_sprints_in_range(date(year, 1, 1), date(year, 12, 31),
                                anchor, prefix, duration_weeks)


def count_days_overlap(sprint_start: date, sprint_end: date,
                       entry_start: str, entry_end: str,
                       state: str, hols: set[date]) -> int:
    """Count work days where a date entry overlaps with a sprint."""
    try:
        es = date.fromisoformat(entry_start)
        ee = date.fromisoformat(entry_end)
    except (ValueError, TypeError):
        return 0
    start = max(sprint_start, es)
    end = min(sprint_end, ee)
    if end < start:
        return 0
    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and cur not in hols:
            count += 1
        cur += timedelta(days=1)
    return count


def capacity_for_sprint(sprint: dict, vac_entries: list[dict],
                        appt_entries: list[dict],
                        blocked_appt_types: list[str],
                        state: str,
                        today: "date | None" = None) -> dict:
    """Calculate capacity breakdown for a single sprint."""
    from modules.vacations.holidays_helper import get_holidays

    ss, se = sprint["start"], sprint["end"]
    hols: set[date] = set()
    for yr in range(ss.year, se.year + 1):
        hols |= get_holidays(yr, state)

    # Total work days in sprint
    total = 0
    cur = ss
    while cur <= se:
        if cur.weekday() < 5 and cur not in hols:
            total += 1
        cur += timedelta(days=1)

    # Holidays overlapping sprint
    holiday_days = sum(1 for d in hols if ss <= d <= se)

    # Vacation approved/documented
    vac_approved = sum(
        count_days_overlap(ss, se, e["start_date"], e["end_date"], state, hols)
        for e in vac_entries
        if e.get("status") in ("approved", "documented")
    )

    # Vacation planned/requested
    vac_planned = sum(
        count_days_overlap(ss, se, e["start_date"], e["end_date"], state, hols)
        for e in vac_entries
        if e.get("status") in ("planned", "requested")
    )

    # Blocked appointments (only configured types)
    blocked_types = set(blocked_appt_types)
    appt_blocked = sum(
        count_days_overlap(ss, se, e["start_date"], e["end_date"], state, hols)
        for e in appt_entries
        if e.get("type") in blocked_types
    )

    remaining = total - vac_approved - appt_blocked
    remaining_after_planned = remaining - vac_planned
    pct = round(remaining / total * 100) if total else 0

    # Available days from today to sprint end (Verfügbar scoped to future portion)
    days_remaining_from_today = 0
    if today is not None and today <= se:
        start_from = max(today, ss)
        cur = start_from
        raw_from_today = 0
        while cur <= se:
            if cur.weekday() < 5 and cur not in hols:
                raw_from_today += 1
            cur += timedelta(days=1)
        vac_remaining = sum(
            count_days_overlap(start_from, se, e["start_date"], e["end_date"], state, hols)
            for e in vac_entries
            if e.get("status") in ("approved", "documented")
        )
        appt_remaining = sum(
            count_days_overlap(start_from, se, e["start_date"], e["end_date"], state, hols)
            for e in appt_entries
            if e.get("type") in blocked_types
        )
        days_remaining_from_today = raw_from_today - vac_remaining - appt_remaining

    return {
        **sprint,
        "total_work_days": total,
        "holiday_days": holiday_days,
        "vac_approved_days": vac_approved,
        "vac_planned_days": vac_planned,
        "appt_blocked_days": appt_blocked,
        "remaining_days": remaining,
        "remaining_after_planned": remaining_after_planned,
        "capacity_pct": pct,
        "days_remaining_from_today": days_remaining_from_today,
    }
