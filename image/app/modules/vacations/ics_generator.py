"""ICS (iCalendar) generation for vacation entries with configurable export profiles."""

import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from modules.vacations.holidays_helper import get_holidays

# Static VTIMEZONE block for Europe/Berlin (needed for timed events)
_VTIMEZONE_BERLIN = """\
BEGIN:VTIMEZONE\r
TZID:Europe/Berlin\r
BEGIN:STANDARD\r
DTSTART:19701025T030000\r
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10\r
TZOFFSETFROM:+0200\r
TZOFFSETTO:+0100\r
TZNAME:CET\r
END:STANDARD\r
BEGIN:DAYLIGHT\r
DTSTART:19700329T020000\r
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3\r
TZOFFSETFROM:+0100\r
TZOFFSETTO:+0200\r
TZNAME:CEST\r
END:DAYLIGHT\r
END:VTIMEZONE\r
"""

_TRANSP = {
    "free": "TRANSPARENT",
    "oof": "OPAQUE",
    "busy": "OPAQUE",
}

_BUSYSTATUS = {
    "free": "FREE",
    "oof": "OOF",
    "busy": "BUSY",
}


def _work_days(start_str: str, end_str: str, state: str) -> list[date]:
    """Return list of working days (Mon-Fri, excluding public holidays) in range."""
    try:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
    except (ValueError, TypeError):
        return []
    if end < start:
        return []

    hols: set[date] = set()
    for year in range(start.year, end.year + 1):
        hols |= get_holidays(year, state)

    days = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in hols:
            days.append(current)
        current += timedelta(days=1)
    return days


def _escape_ics(text: str) -> str:
    """Escape special characters for ICS text values."""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def _fold(line: str) -> str:
    """Fold ICS line at 75 octets (RFC 5545 §3.1)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line + "\r\n"
    result = []
    chunk = b""
    for char in line:
        char_bytes = char.encode("utf-8")
        if len(chunk) + len(char_bytes) > 75:
            result.append(chunk.decode("utf-8") + "\r\n")
            chunk = b" " + char_bytes
        else:
            chunk += char_bytes
    if chunk:
        result.append(chunk.decode("utf-8") + "\r\n")
    return "".join(result)


def _resolve(template: str, entry: dict, work_days: list[date]) -> str:
    """Resolve placeholders like {note}, {start_date}, {end_date}, {days}."""
    replacements: dict[str, str] = defaultdict(
        str,
        {
            "note": entry.get("note", "") or "",
            "start_date": entry.get("start_date", ""),
            "end_date": entry.get("end_date", ""),
            "days": str(len(work_days)),
        },
    )
    return template.format_map(replacements)


def _attendee_lines(required: list[str], optional: list[str]) -> list[str]:
    lines = []
    for email in required:
        lines.append(_fold(f"ATTENDEE;RSVP=FALSE;ROLE=REQ-PARTICIPANT:mailto:{email}"))
    for email in optional:
        lines.append(_fold(f"ATTENDEE;RSVP=FALSE;ROLE=OPT-PARTICIPANT:mailto:{email}"))
    return lines


def _vevent_allday(
    day: date,
    uid_base: str,
    subject: str,
    body: str,
    show_as: str,
    category: str,
    recipients_required: list[str],
    recipients_optional: list[str],
    no_online_meeting: bool,
    dtstamp: str,
) -> str:
    dtstart = day.strftime("%Y%m%d")
    dtend = (day + timedelta(days=1)).strftime("%Y%m%d")
    uid = f"{uid_base}-{dtstart}@daily-helper"

    lines = [
        "BEGIN:VEVENT\r\n",
        _fold(f"UID:{uid}"),
        _fold(f"DTSTAMP:{dtstamp}"),
        _fold(f"DTSTART;VALUE=DATE:{dtstart}"),
        _fold(f"DTEND;VALUE=DATE:{dtend}"),
        _fold(f"SUMMARY:{_escape_ics(subject)}"),
        _fold(f"TRANSP:{_TRANSP.get(show_as, 'OPAQUE')}"),
        _fold(f"X-MICROSOFT-CDO-BUSYSTATUS:{_BUSYSTATUS.get(show_as, 'OOF')}"),
        "CLASS:PUBLIC\r\n",
    ]
    if no_online_meeting:
        lines += ["X-MICROSOFT-SKYPETEAMSMEETINGURL:\r\n", "X-MICROSOFT-ONLINEMEETINGCONFLINK:\r\n"]
    if body:
        lines.append(_fold(f"DESCRIPTION:{_escape_ics(body)}"))
    if category:
        lines.append(_fold(f"CATEGORIES:{_escape_ics(category)}"))
    lines += _attendee_lines(recipients_required, recipients_optional)
    lines.append("END:VEVENT\r\n")
    return "".join(lines)


def _vevent_timed(
    day: date,
    start_time: str,
    end_time: str,
    uid_base: str,
    subject: str,
    body: str,
    show_as: str,
    category: str,
    recipients_required: list[str],
    recipients_optional: list[str],
    no_online_meeting: bool,
    dtstamp: str,
) -> str:
    """Build a timed VEVENT for a single work day."""
    try:
        sh, sm = (int(x) for x in start_time.split(":"))
        eh, em = (int(x) for x in end_time.split(":"))
    except (ValueError, AttributeError):
        sh, sm, eh, em = 8, 0, 17, 0

    dtstart = day.strftime(f"%Y%m%dT{sh:02d}{sm:02d}00")
    dtend = day.strftime(f"%Y%m%dT{eh:02d}{em:02d}00")
    uid = f"{uid_base}-{day.strftime('%Y%m%d')}@daily-helper"

    lines = [
        "BEGIN:VEVENT\r\n",
        _fold(f"UID:{uid}"),
        _fold(f"DTSTAMP:{dtstamp}"),
        _fold(f"DTSTART;TZID=Europe/Berlin:{dtstart}"),
        _fold(f"DTEND;TZID=Europe/Berlin:{dtend}"),
        _fold(f"SUMMARY:{_escape_ics(subject)}"),
        _fold(f"TRANSP:{_TRANSP.get(show_as, 'OPAQUE')}"),
        _fold(f"X-MICROSOFT-CDO-BUSYSTATUS:{_BUSYSTATUS.get(show_as, 'OOF')}"),
        "CLASS:PUBLIC\r\n",
    ]
    if no_online_meeting:
        lines += ["X-MICROSOFT-SKYPETEAMSMEETINGURL:\r\n", "X-MICROSOFT-ONLINEMEETINGCONFLINK:\r\n"]
    if body:
        lines.append(_fold(f"DESCRIPTION:{_escape_ics(body)}"))
    if category:
        lines.append(_fold(f"CATEGORIES:{_escape_ics(category)}"))
    lines += _attendee_lines(recipients_required, recipients_optional)
    lines.append("END:VEVENT\r\n")
    return "".join(lines)


def generate_ics(entry: dict, profile: dict, state: str) -> str:
    """Generate ICS file content for a vacation entry using an export profile."""
    show_as = profile.get("show_as", "oof")
    all_day = profile.get("all_day", True)
    start_time = profile.get("start_time") or "08:00"
    end_time = profile.get("end_time") or "17:00"
    category = profile.get("category") or ""
    # Support old single `recipients` field as fallback
    recipients_required = profile.get("recipients_required") or profile.get("recipients") or []
    recipients_optional = profile.get("recipients_optional") or []
    no_online_meeting = bool(profile.get("no_online_meeting", False))
    subject_tpl = profile.get("subject") or "Vacation {start_date}–{end_date}"
    body_tpl = profile.get("body") or ""

    work_days = _work_days(entry.get("start_date", ""), entry.get("end_date", ""), state)
    subject = _resolve(subject_tpl, entry, work_days)
    body = _resolve(body_tpl, entry, work_days)
    uid_base = entry.get("id", "vacation")
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR\r\n",
        "VERSION:2.0\r\n",
        "PRODID:-//Daily Helper//Vacation//EN\r\n",
        "CALSCALE:GREGORIAN\r\n",
        "METHOD:PUBLISH\r\n",
    ]

    if not all_day:
        lines.append(_VTIMEZONE_BERLIN)

    for day in work_days:
        if all_day:
            lines.append(
                _vevent_allday(
                    day,
                    uid_base,
                    subject,
                    body,
                    show_as,
                    category,
                    recipients_required,
                    recipients_optional,
                    no_online_meeting,
                    dtstamp,
                )
            )
        else:
            lines.append(
                _vevent_timed(
                    day,
                    start_time,
                    end_time,
                    uid_base,
                    subject,
                    body,
                    show_as,
                    category,
                    recipients_required,
                    recipients_optional,
                    no_online_meeting,
                    dtstamp,
                )
            )

    lines.append("END:VCALENDAR\r\n")
    return "".join(lines)


def generate_holiday_ics(holiday_name: str, holiday_date: str, profile: dict) -> str:
    """Generate ICS for a single public holiday using a holiday export profile."""
    show_as = profile.get("show_as", "free")
    subject_tpl = profile.get("subject") or "{name}"
    body_tpl = profile.get("body") or ""
    category = profile.get("category") or ""
    recipients_required = profile.get("recipients_required") or []
    recipients_optional = profile.get("recipients_optional") or []
    no_online_meeting = bool(profile.get("no_online_meeting", False))

    replacements: dict[str, str] = {"name": holiday_name, "date": holiday_date}
    subject = subject_tpl.format_map(replacements)
    body = body_tpl.format_map(replacements)

    try:
        day = date.fromisoformat(holiday_date)
    except (ValueError, TypeError):
        day = date.today()

    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid_base = f"holiday-{holiday_date}"

    lines = [
        "BEGIN:VCALENDAR\r\n",
        "VERSION:2.0\r\n",
        "PRODID:-//Daily Helper//Holiday//EN\r\n",
        "CALSCALE:GREGORIAN\r\n",
        "METHOD:PUBLISH\r\n",
        _vevent_allday(
            day,
            uid_base,
            subject,
            body,
            show_as,
            category,
            recipients_required,
            recipients_optional,
            no_online_meeting,
            dtstamp,
        ),
        "END:VCALENDAR\r\n",
    ]
    return "".join(lines)


def holiday_profile_filename(profile: dict, holiday_date: str, holiday_name: str) -> str:
    """Build filename for a holiday ICS download."""
    profile_part = profile.get("name", "export")
    profile_part = unicodedata.normalize("NFKD", profile_part)
    profile_part = profile_part.encode("ascii", "ignore").decode("ascii")
    profile_part = re.sub(r"[^\w\s-]", "", profile_part).strip().lower()
    profile_part = re.sub(r"[\s_]+", "-", profile_part) or "export"

    name_part = unicodedata.normalize("NFKD", holiday_name)
    name_part = name_part.encode("ascii", "ignore").decode("ascii")
    name_part = re.sub(r"[^\w\s-]", "", name_part).strip().lower()
    name_part = re.sub(r"[\s_]+", "-", name_part) or "holiday"

    return f"{profile_part}_{holiday_date}_{name_part}.ics"


def profile_filename(profile: dict, entry: dict | None = None) -> str:
    """Convert profile name + date range to safe filename.

    E.g. 'Team Kalender', entry 2026-05-01..2026-05-10 → 'team-kalender_2026-05-01_2026-05-10.ics'
    """
    name = profile.get("name", "export")
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^\w\s-]", "", name).strip().lower()
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"-+", "-", name) or "export"
    if entry:
        start = entry.get("start_date", "")
        end = entry.get("end_date", "")
        if start and end:
            name = f"{name}_{start}_{end}"
    return f"{name}.ics"
