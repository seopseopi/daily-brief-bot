"""Derive useful day plans from confirmed data without generating new facts."""

from datetime import datetime, time, timedelta
import re

from sources._shared import KST
from sources.timetable_fixed import DAY_END, DAY_START


_DEADLINE_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d) 마감(?:\s|$)")


def assignment_deadline(item: tuple, now: datetime) -> datetime | None:
    """Read the explicit time prefix emitted by sources.assignments.

    Keep the existing three-item assignment interface. An ordinary note without
    this prefix is not interpreted as a deadline or a duration estimate.
    """
    match = _DEADLINE_TIME.match(item[2] or "")
    if not match:
        return None
    day = now.astimezone(KST).date() + timedelta(days=item[0])
    return datetime.combine(day, time(int(match[1]), int(match[2])), KST)


def assignment_is_overdue(item: tuple, now: datetime) -> bool:
    deadline = assignment_deadline(item, now)
    return item[0] < 0 or (deadline is not None and deadline <= now)


def plan_day(now: datetime, schedule: dict, assignments: list) -> dict:
    """Find remaining conflicts and free time within the configured day.

    Transparent events are reminders, not reservations. All-day busy events
    block the day. Partial calendars can show known conflicts but cannot
    establish that a time is free. No claim is made about travel time.
    """
    now = now.astimezone(KST)
    start = max(now, datetime.combine(now.date(), time.fromisoformat(DAY_START), KST))
    # Round up so a recommended slot never starts in the past.
    if start.second or start.microsecond:
        start = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = datetime.combine(now.date(), time.fromisoformat(DAY_END), KST)
    events = sorted(
        (event for event in schedule.get("events", [])
         if not event.get("transparent") and event["end"] > now),
        key=lambda event: (event["start"], event["end"], event["name"]),
    )
    conflicts = []
    timed = [event for event in events if not event.get("all_day")]
    for index, first in enumerate(timed):
        for second in timed[index + 1:]:
            if second["start"] >= first["end"]:
                break
            overlap_start = max(now, first["start"], second["start"])
            overlap_end = min(first["end"], second["end"])
            if overlap_end > overlap_start:
                conflicts.append({"names": [first["name"], second["name"]],
                                  "start": overlap_start, "end": overlap_end})

    free = []
    if schedule.get("status") == "fresh" and start < end:
        busy = sorted((max(start, event["start"]), min(end, event["end"]))
                      for event in events if event["start"] < end and event["end"] > start)
        cursor = start
        for busy_start, busy_end in busy:
            if busy_start - cursor >= timedelta(minutes=30):
                free.append({"start": cursor, "end": busy_start})
            cursor = max(cursor, busy_end)
        if end - cursor >= timedelta(minutes=30):
            free.append({"start": cursor, "end": end})
    for slot in free:
        slot["minutes"] = int((slot["end"] - slot["start"]).total_seconds() // 60)

    deadlines = sorted(assignments, key=lambda item: (
        item[0],
        assignment_deadline(item, now) or datetime.combine(
            now.date() + timedelta(days=item[0]), time.max, KST),
        item[1],
    ))
    overdue = [item for item in deadlines if assignment_is_overdue(item, now)]
    focus_slot = free[0] if free else None
    focus_task = None
    focus_end = None
    if focus_slot:
        for item in deadlines:
            if assignment_is_overdue(item, now):
                continue
            deadline = assignment_deadline(item, now)
            if deadline is not None and deadline <= focus_slot["start"]:
                continue
            focus_task = item
            focus_end = focus_slot["start"] + timedelta(minutes=min(50, focus_slot["minutes"]))
            if deadline is not None:
                focus_end = min(focus_end, deadline)
            break
    return {"conflicts": conflicts, "free_slots": free,
            "due_soon": [item for item in deadlines if 0 <= item[0] <= 7 and item not in overdue],
            "overdue": overdue,
            "focus_slot": focus_slot, "focus_task": focus_task, "focus_end": focus_end,
            "calendar_complete": schedule.get("status") == "fresh"}
