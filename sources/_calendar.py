"""Read-only iCalendar feed support.

The private iCal URL is a credential. This module never logs or returns it.
Recurring events are expanded with ``recurring-ical-events`` so exceptions and
cancelled instances from Google Calendar are respected.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import time as time_module
import urllib.error
import urllib.request

from http_client import open_url

from sources._shared import KST

USER_AGENT = "MorningBriefBot/2.0"
TIMEOUT = 15
ATTEMPTS = 2


def fetch_ics(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    raw = None
    last_error = None
    for attempt in range(ATTEMPTS):
        try:
            with open_url(req, timeout=TIMEOUT) as response:
                raw = response.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        if attempt < ATTEMPTS - 1:
            time_module.sleep(0.5)
    if raw is None:
        raise last_error or RuntimeError("calendar request failed")
    if b"BEGIN:VCALENDAR" not in raw:
        raise ValueError("response is not an iCalendar document")
    return raw


def _as_datetime(value, *, is_end: bool = False) -> tuple[datetime, bool]:
    """Return a KST-aware datetime and whether the source value was all-day."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=KST)
        return value.astimezone(KST), False
    if isinstance(value, date):
        return datetime.combine(value, time.min, KST), True
    raise ValueError(f"unsupported calendar date value: {type(value).__name__}")


def parse_events(raw: bytes, start: datetime, end: datetime) -> tuple[str, list[dict]]:
    """Expand and normalize events overlapping ``[start, end)``."""
    try:
        from icalendar import Calendar
        import recurring_ical_events
    except ImportError as exc:  # clearer than a mysterious calendar failure
        raise RuntimeError("calendar dependencies are not installed") from exc

    calendar = Calendar.from_ical(raw)
    name = str(calendar.get("X-WR-CALNAME") or "연결된 캘린더")
    components = recurring_ical_events.of(calendar).between(start, end)
    events = []
    for component in components:
        if str(component.get("STATUS", "")).upper() == "CANCELLED":
            continue
        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue
        event_start, all_day = _as_datetime(dtstart.dt)
        dtend = component.get("DTEND")
        if dtend is not None:
            event_end, _ = _as_datetime(dtend.dt, is_end=True)
        else:
            duration = component.get("DURATION")
            event_end = event_start + (duration.dt if duration is not None else timedelta(days=1 if all_day else 0))

        # Some recurrence libraries return starts just outside the range. Keep
        # overlapping events only, including events that started yesterday.
        if event_end <= start or event_start >= end:
            continue

        uid = str(component.get("UID") or "")
        transparent = str(component.get("TRANSP") or "OPAQUE").upper() == "TRANSPARENT"
        events.append({
            "uid": uid,
            "name": str(component.get("SUMMARY") or "(제목 없는 일정)").strip(),
            "start": event_start,
            "end": event_end,
            "all_day": all_day,
            "location": str(component.get("LOCATION") or "").strip(),
            "calendar": name,
            "last_modified": _component_datetime(component, "LAST-MODIFIED"),
            "transparent": transparent,
        })

    # Multiple subscribed feeds occasionally expose the same invitation.
    unique = {}
    for event in events:
        key = (event["uid"] or event["name"], event["start"], event["end"])
        unique[key] = event
    return name, sorted(unique.values(), key=lambda event: (event["start"], event["end"], event["name"]))


def _component_datetime(component, key: str) -> datetime | None:
    value = component.get(key)
    if value is None:
        return None
    try:
        return _as_datetime(value.dt)[0]
    except (AttributeError, ValueError):
        return None
