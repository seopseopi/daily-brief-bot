"""Optional private weekly timetable loaded from the environment.

Set ``FIXED_TIMETABLE_JSON`` to an object whose keys are weekdays (``0`` is
Monday, ``6`` is Sunday) and whose values are event arrays:

``{"0": [["09:00", "10:30", "event name", "optional note"]]}``

No personal schedule is kept in the public source tree. Invalid input fails
closed to an empty timetable and its contents are never logged.
"""

from __future__ import annotations

import json
import re

import settings

DAY_START = "09:00"
DAY_END = "23:00"

_TIME_PATTERN = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
_MAX_CONFIG_CHARS = 100_000
_MAX_EVENTS_PER_DAY = 50
_MAX_NAME_CHARS = 200
_MAX_NOTE_CHARS = 500


def _minutes(value: str) -> int:
    hours, minutes = (int(part) for part in value.split(":"))
    return hours * 60 + minutes


def parse_fixed_timetable(raw: str) -> dict[int, list[tuple[str, str, str, str]]]:
    """Validate private timetable JSON.

    An unset/blank value is the only normal empty timetable. Malformed input
    raises a generic ``ValueError`` so the schedule section cannot present an
    incomplete configuration as fresh. Error text never contains user data.
    """
    if isinstance(raw, str) and not raw.strip():
        return {}
    if not isinstance(raw, str) or len(raw) > _MAX_CONFIG_CHARS:
        raise ValueError("FIXED_TIMETABLE_JSON has an invalid size or type")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        raise ValueError("FIXED_TIMETABLE_JSON is not valid JSON") from None
    if not isinstance(value, dict):
        raise ValueError("FIXED_TIMETABLE_JSON schema is invalid")

    parsed: dict[int, list[tuple[str, str, str, str]]] = {}
    try:
        for raw_day, raw_events in value.items():
            if not isinstance(raw_day, str) or not raw_day.isdigit():
                raise ValueError("weekday keys must be numeric strings")
            day = int(raw_day)
            if day not in range(7) or not isinstance(raw_events, list):
                raise ValueError("weekday/event-list shape is invalid")
            if len(raw_events) > _MAX_EVENTS_PER_DAY:
                raise ValueError("too many events")

            events = []
            for raw_event in raw_events:
                if not isinstance(raw_event, list) or len(raw_event) not in {3, 4}:
                    raise ValueError("event must contain start, end, name, optional note")
                if not all(isinstance(part, str) for part in raw_event):
                    raise ValueError("event fields must be strings")
                start, end, name = (part.strip() for part in raw_event[:3])
                note = raw_event[3].strip() if len(raw_event) == 4 else ""
                if not _TIME_PATTERN.fullmatch(start) or not _TIME_PATTERN.fullmatch(end):
                    raise ValueError("invalid time")
                if _minutes(end) <= _minutes(start):
                    raise ValueError("event end must follow start")
                if not name or len(name) > _MAX_NAME_CHARS or len(note) > _MAX_NOTE_CHARS:
                    raise ValueError("invalid event text")
                events.append((start, end, name, note))

            events.sort(key=lambda event: (_minutes(event[0]), _minutes(event[1]), event[2]))
            for previous, current in zip(events, events[1:]):
                if _minutes(current[0]) < _minutes(previous[1]):
                    raise ValueError("overlapping fixed events")
            parsed[day] = events
    except (TypeError, ValueError):
        raise ValueError("FIXED_TIMETABLE_JSON schema is invalid") from None
    return parsed


FIXED_TIMETABLE_ERROR = None
try:
    FIXED_TIMETABLE = parse_fixed_timetable(settings.FIXED_TIMETABLE_JSON)
except ValueError:
    # Keep imports safe, but make the configuration failure explicit to
    # schedule.get_schedule(). Never retain or log the invalid content here.
    FIXED_TIMETABLE = {}
    FIXED_TIMETABLE_ERROR = "invalid"
