"""Today's personal calendar from private iCalendar feeds or a fixed timetable.

Set ``CALENDAR_ICS_URLS`` to one or more newline-separated private iCal URLs.
The environment-backed fixed timetable is used only when configured, unless
``INCLUDE_FIXED_TIMETABLE=false`` explicitly disables it.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import settings
from sources import _calendar
from sources._shared import KST, fail
from sources.timetable_fixed import DAY_END, DAY_START, FIXED_TIMETABLE, FIXED_TIMETABLE_ERROR


def _fixed_events(now: datetime) -> list[dict]:
    events = []
    for start_text, end_text, name, detail in FIXED_TIMETABLE.get(now.weekday(), []):
        start_hour, start_minute = map(int, start_text.split(":"))
        end_hour, end_minute = map(int, end_text.split(":"))
        events.append({
            "uid": f"fixed:{now.date()}:{start_text}:{name}",
            "name": name,
            "start": datetime.combine(now.date(), time(start_hour, start_minute), KST),
            "end": datetime.combine(now.date(), time(end_hour, end_minute), KST),
            "all_day": False,
            "location": detail,
            "calendar": "고정 시간표",
            "last_modified": None,
            "transparent": False,
        })
    return events


def _free_slots(events: list[dict], now: datetime) -> str:
    day_start = datetime.combine(now.date(), time.fromisoformat(DAY_START), KST)
    day_end = datetime.combine(now.date(), time.fromisoformat(DAY_END), KST)
    blocking_events = [event for event in events if not event.get("transparent", False)]
    if any(event["all_day"] for event in blocking_events):
        return "종일 일정 있음"

    busy = []
    for event in blocking_events:
        start = max(event["start"], day_start)
        end = min(event["end"], day_end)
        if end > start:
            busy.append((start, end))
    busy.sort()

    merged = []
    for start, end in busy:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))

    slots = []
    cursor = day_start
    for start, end in merged:
        if start - cursor >= timedelta(minutes=30):
            hours = (start - cursor).total_seconds() / 3600
            slots.append(f"{cursor:%H:%M}~{start:%H:%M} ({hours:g}h)")
        cursor = max(cursor, end)
    if day_end - cursor >= timedelta(minutes=30):
        hours = (day_end - cursor).total_seconds() / 3600
        slots.append(f"{cursor:%H:%M}~{day_end:%H:%M} ({hours:g}h)")

    if slots:
        return " · ".join(slots)
    return "빈 시간 없음" if events else "09:00~23:00"


def get_schedule(now: datetime | None = None) -> dict:
    now = (now or datetime.now(KST)).astimezone(KST)
    start = datetime.combine(now.date(), time.min, KST)
    end = start + timedelta(days=1)
    events = []
    calendars = []
    errors = 0

    for url in settings.CALENDAR_ICS_URLS:
        try:
            raw = _calendar.fetch_ics(url)
            calendar_name, calendar_events = _calendar.parse_events(raw, start, end)
            calendars.append(calendar_name)
            events.extend(calendar_events)
        except Exception as exc:
            # Never print the private URL. Exception text from HTTP clients can
            # contain it, so only the class is logged.
            print(f"[경고] 캘린더 조회 실패: {type(exc).__name__}")
            errors += 1
            fail("개인 캘린더")

    fixed_requested = settings.INCLUDE_FIXED_TIMETABLE
    fixed_succeeded = False
    if fixed_requested and FIXED_TIMETABLE_ERROR:
        print("[경고] 고정 시간표 설정 실패: ValueError")
        errors += 1
        fail("고정 시간표 설정")
    elif fixed_requested:
        events.extend(_fixed_events(now))
        fixed_succeeded = True

    unique = {}
    for event in events:
        # Prefer a real calendar event when the fallback timetable duplicates it.
        key = (event["name"].lower().strip(), event["start"], event["end"])
        if key not in unique or unique[key]["calendar"] == "고정 시간표":
            unique[key] = event
    events = sorted(unique.values(), key=lambda event: (event["start"], event["end"], event["name"]))

    configured = bool(settings.CALENDAR_ICS_URLS)
    configured_sources = len(settings.CALENDAR_ICS_URLS) + int(fixed_requested)
    successful_sources = len(calendars) + int(fixed_succeeded)
    if configured_sources == 0:
        status = "unconfigured"
    elif successful_sources == 0:
        status = "unavailable"
    elif errors:
        status = "partial"
    else:
        status = "fresh"

    source_parts = calendars[:]
    if fixed_requested and FIXED_TIMETABLE_ERROR:
        source_parts.append("고정 시간표 설정 오류")
    elif fixed_requested:
        source_parts.append("개인 캘린더 · 고정 시간표")

    return {
        "events": events,
        "free_slots": _free_slots(events, now),
        "status": status,
        "calendar_configured": configured,
        "fixed_timetable_used": fixed_succeeded,
        "source": " · ".join(source_parts) or "일정 소스 미연결",
        "as_of": now,
    }
