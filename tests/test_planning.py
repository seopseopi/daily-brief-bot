import unittest
from datetime import datetime, timedelta

from briefing.planning import assignment_deadline, plan_day
from sources._shared import KST


NOW = datetime(2026, 9, 13, 9, tzinfo=KST)


def event(name, start, end, **extra):
    return {"name": name, "start": NOW.replace(hour=start),
            "end": NOW.replace(hour=end), "all_day": False, **extra}


class DayPlanningTests(unittest.TestCase):
    def test_partial_calendar_can_report_conflicts_but_not_free_time(self):
        result = plan_day(NOW, {"status": "partial", "events": [
            event("수업", 10, 12), event("회의", 11, 13),
        ]}, [(0, "과제", "")])

        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(result["conflicts"][0]["start"], NOW.replace(hour=11))
        self.assertEqual(result["free_slots"], [])
        self.assertIsNone(result["focus_task"])
        self.assertFalse(result["calendar_complete"])

    def test_busy_all_day_blocks_free_time_but_transparent_reminder_does_not(self):
        all_day = {"name": "종일 일정", "start": NOW.replace(hour=0),
                   "end": NOW.replace(hour=0) + timedelta(days=1), "all_day": True}
        for transparent in (False, True):
            with self.subTest(transparent=transparent):
                result = plan_day(NOW, {"status": "fresh", "events": [
                    dict(all_day, transparent=transparent),
                ]}, [])
                self.assertEqual(bool(result["free_slots"]), transparent)

    def test_focus_never_starts_in_the_past(self):
        now = NOW.replace(second=30)
        result = plan_day(now, {"status": "fresh", "events": []}, [(0, "과제", "")])

        self.assertEqual(result["focus_slot"]["start"], NOW.replace(minute=1))

    def test_explicit_deadline_before_first_free_slot_is_not_recommended(self):
        result = plan_day(NOW, {"status": "fresh", "events": [event("일정", 9, 18)]}, [
            (0, "오늘 과제", "17:00 마감"),
        ])

        self.assertEqual(result["focus_slot"]["start"].hour, 18)
        self.assertIsNone(result["focus_task"])
        self.assertIsNone(result["focus_end"])

    def test_focus_ends_before_deadline_and_uses_time_order_not_name_order(self):
        earlier = (0, "후순위 이름", "09:20 마감 · 제출")
        later = (0, "가장 앞 이름", "17:00 마감")
        result = plan_day(NOW, {"status": "fresh", "events": []}, [later, earlier])

        self.assertEqual(result["focus_task"], earlier)
        self.assertEqual(result["focus_end"], NOW.replace(minute=20))

    def test_passed_today_deadline_is_overdue_and_next_valid_task_is_recommended(self):
        overdue = (0, "시간 지난 과제", "08:30 마감")
        upcoming = (1, "내일 과제", "")
        result = plan_day(NOW, {"status": "fresh", "events": []}, [overdue, upcoming])

        self.assertEqual(result["overdue"], [overdue])
        self.assertEqual(result["due_soon"], [upcoming])
        self.assertEqual(result["focus_task"], upcoming)

    def test_ordinary_note_is_not_guessed_to_be_a_deadline(self):
        self.assertIsNone(assignment_deadline((0, "과제", "이전 공지에는 08:00 마감"), NOW))


if __name__ == "__main__":
    unittest.main()
