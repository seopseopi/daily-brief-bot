import io
import textwrap
import unittest
from datetime import datetime, timedelta
from unittest import mock

import settings
from sources import _calendar, schedule
from sources._shared import KST, get_failures


NOW = datetime(2026, 9, 11, 7, 30, tzinfo=KST)
DAY_START = NOW.replace(hour=0, minute=0)
DAY_END = DAY_START + timedelta(days=1)


ICS_FIXTURE = textwrap.dedent(
    """\
    BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//Morning Brief Tests//EN
    X-WR-CALNAME:테스트 캘린더
    BEGIN:VEVENT
    UID:weekly-kept
    DTSTAMP:20260901T000000Z
    DTSTART;TZID=Asia/Seoul:20260904T090000
    DTEND;TZID=Asia/Seoul:20260904T100000
    RRULE:FREQ=WEEKLY;COUNT=3
    SUMMARY:반복 수업
    LOCATION:미래관
    LAST-MODIFIED:20260910T230000Z
    END:VEVENT
    BEGIN:VEVENT
    UID:weekly-cancelled
    DTSTAMP:20260901T000000Z
    DTSTART;TZID=Asia/Seoul:20260904T100000
    DTEND;TZID=Asia/Seoul:20260904T110000
    RRULE:FREQ=WEEKLY;COUNT=3
    SUMMARY:취소 대상 수업
    END:VEVENT
    BEGIN:VEVENT
    UID:weekly-cancelled
    DTSTAMP:20260910T000000Z
    RECURRENCE-ID;TZID=Asia/Seoul:20260911T100000
    DTSTART;TZID=Asia/Seoul:20260911T100000
    DTEND;TZID=Asia/Seoul:20260911T110000
    STATUS:CANCELLED
    SUMMARY:취소 대상 수업
    END:VEVENT
    BEGIN:VEVENT
    UID:all-day-event
    DTSTAMP:20260901T000000Z
    DTSTART;VALUE=DATE:20260911
    DTEND;VALUE=DATE:20260912
    SUMMARY:종일 행사
    END:VEVENT
    BEGIN:VEVENT
    UID:standalone-cancelled
    DTSTAMP:20260901T000000Z
    DTSTART;TZID=Asia/Seoul:20260911T130000
    DTEND;TZID=Asia/Seoul:20260911T140000
    STATUS:CANCELLED
    SUMMARY:취소된 단일 일정
    END:VEVENT
    END:VCALENDAR
    """
).replace("\n", "\r\n").encode("utf-8")

TRANSPARENT_ALL_DAY_FIXTURE = textwrap.dedent(
    """\
    BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//Morning Brief Tests//EN
    X-WR-CALNAME:휴일 캘린더
    BEGIN:VEVENT
    UID:transparent-holiday
    DTSTAMP:20260901T000000Z
    DTSTART;VALUE=DATE:20260911
    DTEND;VALUE=DATE:20260912
    TRANSP:TRANSPARENT
    SUMMARY:공휴일 안내
    END:VEVENT
    END:VCALENDAR
    """
).replace("\n", "\r\n").encode("utf-8")


class CalendarFixtureTests(unittest.TestCase):
    def setUp(self):
        get_failures()

    def tearDown(self):
        get_failures()

    def test_recurring_cancelled_and_all_day_events_are_normalized(self):
        name, events = _calendar.parse_events(ICS_FIXTURE, DAY_START, DAY_END)

        self.assertEqual(name, "테스트 캘린더")
        self.assertEqual([event["name"] for event in events], ["종일 행사", "반복 수업"])

        all_day, recurring = events
        self.assertTrue(all_day["all_day"])
        self.assertEqual(all_day["start"], DAY_START)
        self.assertEqual(all_day["end"], DAY_END)
        self.assertFalse(recurring["all_day"])
        self.assertEqual(recurring["start"], NOW.replace(hour=9, minute=0))
        self.assertEqual(recurring["end"], NOW.replace(hour=10, minute=0))
        self.assertEqual(recurring["location"], "미래관")
        self.assertEqual(recurring["last_modified"], NOW.replace(hour=8, minute=0))

    def test_schedule_uses_calendar_fixture_without_fixed_timetable(self):
        with (
            mock.patch.object(settings, "CALENDAR_ICS_URLS", ["https://secret.example/calendar.ics"]),
            mock.patch.object(settings, "INCLUDE_FIXED_TIMETABLE", False),
            mock.patch.object(_calendar, "fetch_ics", return_value=ICS_FIXTURE),
        ):
            result = schedule.get_schedule(NOW)

        self.assertEqual(result["status"], "fresh")
        self.assertTrue(result["calendar_configured"])
        self.assertEqual(result["source"], "테스트 캘린더")
        self.assertEqual([event["name"] for event in result["events"]], ["종일 행사", "반복 수업"])
        self.assertEqual(result["free_slots"], "종일 일정 있음")
        self.assertEqual(result["as_of"], NOW)

    def test_transparent_all_day_event_does_not_block_free_slots(self):
        _name, events = _calendar.parse_events(
            TRANSPARENT_ALL_DAY_FIXTURE,
            DAY_START,
            DAY_END,
        )

        result = schedule._free_slots(events, NOW)

        self.assertTrue(events[0]["all_day"])
        self.assertTrue(events[0]["transparent"])
        self.assertEqual(result, "09:00~23:00 (14h)")

    def test_partial_failure_does_not_log_private_calendar_url(self):
        secret_url = "https://secret.example/private-token/calendar.ics"
        with (
            mock.patch.object(settings, "CALENDAR_ICS_URLS", ["https://ok.example/a.ics", secret_url]),
            mock.patch.object(settings, "INCLUDE_FIXED_TIMETABLE", False),
            mock.patch.object(
                _calendar,
                "fetch_ics",
                side_effect=[ICS_FIXTURE, OSError(f"failed to fetch {secret_url}")],
            ),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            result = schedule.get_schedule(NOW)

        self.assertEqual(result["status"], "partial")
        self.assertNotIn(secret_url, stdout.getvalue())
        self.assertIn("OSError", stdout.getvalue())

    def test_all_configured_calendars_failing_is_unavailable(self):
        with (
            mock.patch.object(settings, "CALENDAR_ICS_URLS", ["https://secret.example/a.ics"]),
            mock.patch.object(settings, "INCLUDE_FIXED_TIMETABLE", False),
            mock.patch.object(_calendar, "fetch_ics", side_effect=TimeoutError),
        ):
            result = schedule.get_schedule(NOW)

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["events"], [])
        self.assertIn("개인 캘린더", get_failures())

    def test_invalid_fixed_timetable_is_reported_as_unavailable(self):
        with (
            mock.patch.object(settings, "CALENDAR_ICS_URLS", []),
            mock.patch.object(settings, "INCLUDE_FIXED_TIMETABLE", True),
            mock.patch.object(schedule, "FIXED_TIMETABLE", {}),
            mock.patch.object(schedule, "FIXED_TIMETABLE_ERROR", "invalid"),
        ):
            result = schedule.get_schedule(NOW)

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["events"], [])
        self.assertIn("설정 오류", result["source"])
        self.assertIn("고정 시간표 설정", get_failures())

    def test_no_private_schedule_source_is_unconfigured_not_fresh(self):
        with (
            mock.patch.object(settings, "CALENDAR_ICS_URLS", []),
            mock.patch.object(settings, "INCLUDE_FIXED_TIMETABLE", False),
        ):
            result = schedule.get_schedule(NOW)

        self.assertEqual(result["status"], "unconfigured")
        self.assertEqual(result["events"], [])
        self.assertEqual(result["source"], "일정 소스 미연결")


if __name__ == "__main__":
    unittest.main()
