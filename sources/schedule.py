"""일정 섹션 — 고정 시간표에서 오늘 것만 뽑는다."""

from datetime import datetime

from sources._shared import KST
from sources.timetable_fixed import DAY_END, DAY_START, FIXED_TIMETABLE


def _to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def get_schedule():
    """고정 시간표(sources/timetable_fixed.py)에서 오늘 요일 것만 뽑는다.

    구글 캘린더 대신 매주 반복되는 수업·알바 시간을 하드코딩해 쓴다.
    시간이 바뀌면 timetable_fixed.py만 고치면 된다.
    """
    weekday = datetime.now(KST).weekday()  # 0=월 ... 6=일
    today = FIXED_TIMETABLE.get(weekday, [])

    events = [(f"{s}–{e}", name, detail) for s, e, name, detail in today]

    slots = []
    cursor = _to_minutes(DAY_START)
    day_end = _to_minutes(DAY_END)
    for s, e, _name, _detail in today:
        s_m, e_m = _to_minutes(s), _to_minutes(e)
        if s_m > cursor and s_m - cursor >= 30:
            hours = (s_m - cursor) / 60
            slots.append(f"{_to_hhmm(cursor)}~{_to_hhmm(s_m)} ({hours:g}h)")
        cursor = max(cursor, e_m)
    if day_end > cursor and day_end - cursor >= 30:
        hours = (day_end - cursor) / 60
        slots.append(f"{_to_hhmm(cursor)}~{_to_hhmm(day_end)} ({hours:g}h)")

    if slots:
        free_slots = " · ".join(slots)
    elif today:
        free_slots = "빈 시간 없음"
    else:
        free_slots = "오늘은 고정 일정 없음"

    return {"events": events, "free_slots": free_slots}
