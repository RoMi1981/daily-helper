"""Helpers for German public holidays and workday calculation."""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def get_holidays(year: int, state: str, language: str = "de") -> set[date]:
    """Return all public holidays for a year and German state."""
    try:
        import holidays

        h = holidays.Germany(subdiv=state, years=year, language=language)
        return set(h.keys())
    except Exception as e:
        logger.warning("Failed to load holidays for %s %d: %s", state, year, e)
        return set()


def count_work_days(start: str, end: str, state: str) -> int:
    """Count working days (Mon–Fri, excluding public holidays) between start and end (inclusive)."""
    try:
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
    except (ValueError, TypeError):
        return 0
    if end_d < start_d:
        return 0

    hols: set[date] = set()
    for year in range(start_d.year, end_d.year + 1):
        hols |= get_holidays(year, state)

    count = 0
    current = start_d
    while current <= end_d:
        if current.weekday() < 5 and current not in hols:
            count += 1
        current += timedelta(days=1)
    return count


def get_calendar_data(
    year: int,
    month: int,
    state: str,
    vacation_entries: list[dict],
    language: str = "de",
    appointment_entries: list[dict] | None = None,
    task_entries: list[dict] | None = None,
    sprint_anchor: "date | None" = None,
    sprint_prefix: str = "PFM Sprint",
    sprint_duration_weeks: int = 3,
) -> dict:
    """Build calendar data for a given month.

    Optional appointment_entries are shown as an overlay on the calendar.
    """
    import calendar

    hols = get_holidays(year, state, language)
    vacation_days: set[date] = set()  # approved + documented
    pending_days: set[date] = set()  # planned + requested

    for entry in vacation_entries:
        status = entry.get("status", "")
        if status not in ("approved", "documented", "planned", "requested"):
            continue
        try:
            s = date.fromisoformat(entry["start_date"])
            e = date.fromisoformat(entry["end_date"])
        except (ValueError, KeyError):
            continue
        cur = s
        while cur <= e:
            if cur.year == year and cur.month == month:
                if status in ("approved", "documented"):
                    vacation_days.add(cur)
                else:
                    pending_days.add(cur)
            cur += timedelta(days=1)

    # Build task due-date map: date → list of task dicts (open tasks only)
    task_days: dict[date, list[dict]] = {}
    for task in task_entries or []:
        if task.get("done"):
            continue
        due = task.get("due_date", "")
        if not due:
            continue
        try:
            d = date.fromisoformat(due)
        except ValueError:
            continue
        if d.year == year and d.month == month:
            task_days.setdefault(d, []).append(task)

    # Build appointment day map: date → list of appointment entries
    appt_days: dict[date, list[dict]] = {}
    for entry in appointment_entries or []:
        try:
            s = date.fromisoformat(entry["start_date"])
            e = date.fromisoformat(entry["end_date"])
        except (ValueError, KeyError):
            continue
        cur = s
        while cur <= e:
            if cur.year == year and cur.month == month:
                appt_days.setdefault(cur, []).append(entry)
            cur += timedelta(days=1)

    # Build sprint-start set for this month
    sprint_starts: dict[date, str] = {}
    if sprint_anchor is not None:
        from modules.calendar.sprint_helper import get_sprints_in_range
        from datetime import date as _date
        import calendar as _cal

        last_day = _cal.monthrange(year, month)[1]
        month_start = _date(year, month, 1)
        month_end = _date(year, month, last_day)
        for sp in get_sprints_in_range(
            month_start, month_end, sprint_anchor, sprint_prefix, sprint_duration_weeks
        ):
            if sp["start"].year == year and sp["start"].month == month:
                sprint_starts[sp["start"]] = sp["name"]

    cal = calendar.monthcalendar(year, month)
    weeks = []
    for week in cal:
        days = []
        for dow, day_num in enumerate(week):
            if day_num == 0:
                days.append(None)
                continue
            d = date(year, month, day_num)
            days.append(
                {
                    "date": d,
                    "day": day_num,
                    "is_weekend": dow >= 5,
                    "is_holiday": d in hols,
                    "holiday_name": _holiday_name(d, state, language),
                    "is_vacation": d in vacation_days,
                    "is_vacation_pending": d in pending_days and d not in vacation_days,
                    "is_appointment": d in appt_days,
                    "appointments": appt_days.get(d, []),
                    "is_today": d == date.today(),
                    "tasks": task_days.get(d, []),
                    "sprint_name": sprint_starts.get(d),
                }
            )
        weeks.append(days)

    prev_month = month - 1 or 12
    prev_year = year - 1 if month == 1 else year
    next_month = month % 12 + 1
    next_year = year + 1 if month == 12 else year

    _month_names_de = [
        "",
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ]
    _month_names_en = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    _weekday_de = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    _weekday_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    if language == "en":
        month_name = _month_names_en[month]
        weekday_headers = _weekday_en
    else:
        month_name = _month_names_de[month]
        weekday_headers = _weekday_de

    return {
        "year": year,
        "month": month,
        "month_name": month_name,
        "weeks": weeks,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "weekday_headers": weekday_headers,
    }


def _holiday_name(d: date, state: str, language: str = "de") -> str:
    try:
        import holidays

        h = holidays.Germany(subdiv=state, years=d.year, language=language)
        return h.get(d, "")
    except Exception:
        return ""
