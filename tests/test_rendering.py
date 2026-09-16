import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from unittest import mock

from briefing import rendering
from sources._shared import KST, get_failures


NOW = datetime(2026, 9, 13, 9, tzinfo=KST)


def event(name, start, end, **extra):
    return {"name": name, "start": NOW.replace(hour=start),
            "end": NOW.replace(hour=end), "all_day": False, **extra}


class RenderingRegressionTests(unittest.TestCase):
    def setUp(self):
        get_failures()

    def tearDown(self):
        get_failures()

    def test_empty_notices_stay_visible_and_distinguish_failed_lookup(self):
        for status in ("ok", "partial"):
            data = {"notices": [], "_source_health": {"notices": {"status": status}}}
            with mock.patch.object(rendering.settings, "ENABLED_SECTIONS", {"notices"}):
                embeds = rendering.render_sections(NOW, data)
            self.assertEqual(len(embeds), 1)
            body = embeds[0]["description"]
            if status == "ok":
                self.assertIn("새 공지가 없습니다", body)
            else:
                self.assertIn("누락될 수 있습니다", body)
                self.assertNotIn("새 공지가 없습니다", body)

    def test_compact_bad_section_does_not_discard_healthy_sections(self):
        for value in (None, 42):
            with self.subTest(value=value):
                data = {"news": value, "schedule": {"status": "fresh", "events": []}}
                with mock.patch.object(rendering.settings, "ENABLED_SECTIONS", {"schedule", "news"}):
                    embeds = rendering.render_sections(NOW, data, compact=True)

                self.assertEqual(len(embeds), 2)
                self.assertEqual(embeds[0]["title"], "📅 오늘 일정 · 마감")
                self.assertEqual(embeds[1]["title"], "⚠️ 시사")
                self.assertEqual(data["_render_failed"], ["news"])

    def test_compact_only_processes_enabled_sections(self):
        data = {"community": 42, "schedule": {"status": "fresh", "events": []}}
        with mock.patch.object(rendering.settings, "ENABLED_SECTIONS", {"schedule"}):
            embeds = rendering.render_sections(NOW, data, compact=True)

        self.assertEqual(len(embeds), 1)
        self.assertNotIn("_render_failed", data)

    def test_notice_render_failure_is_recorded_for_delivery_acknowledgment(self):
        data = {"notices": [("학사", [("broken row",)])]}
        with mock.patch.object(rendering.settings, "ENABLED_SECTIONS", {"notices"}):
            embeds = rendering.render_sections(NOW, data, compact=False)

        self.assertEqual(data["_render_failed"], ["notices"])
        self.assertEqual(embeds[0]["title"], "⚠️ 학사 공지")

    def test_all_day_reminder_does_not_hide_next_timed_event(self):
        all_day = {"name": "종일 알림", "start": NOW.replace(hour=0),
                   "end": NOW.replace(hour=0) + timedelta(days=1),
                   "all_day": True, "transparent": True}
        data = {"schedule": {"status": "fresh", "events": [
            all_day, event("다음 회의", 10, 11),
        ]}}

        highlights = rendering._deterministic_highlights(NOW, data)

        self.assertEqual(highlights[0], ("다음 일정 10:00", "다음 회의"))

    def test_active_timed_event_still_precedes_next_timed_event(self):
        data = {"schedule": {"status": "fresh", "events": [
            event("다음 회의", 10, 11), event("진행 중 수업", 8, 10),
        ]}}

        highlights = rendering._deterministic_highlights(NOW, data)

        self.assertEqual(highlights[0], ("진행 중 · 10:00 종료", "진행 중 수업"))

    def test_today_passed_time_is_marked_overdue_without_preparation_suggestion(self):
        tasks = [(0, "마감 지난 과제", "08:30 마감")]
        schedule = {"status": "fresh", "events": []}

        embed = rendering.build_schedule(schedule, tasks, NOW)
        highlights = rendering._deterministic_highlights(NOW, {"schedule": schedule, "assignments": tasks})

        self.assertIn("기한 지남", embed["description"])
        self.assertNotIn("먼저 시작할 일", embed["description"])
        self.assertEqual(highlights[0][0], "연체 과제 1개")

    def test_does_not_suggest_preparation_after_known_deadline(self):
        embed = rendering.build_schedule(
            {"status": "fresh", "events": [event("일정", 9, 18)]},
            [(0, "과제", "17:00 마감")], NOW,
        )

        self.assertNotIn("먼저 시작할 일", embed["description"])
        self.assertIn("17:00 마감", embed["description"])

    def test_compact_keeps_input_source_payload_intact(self):
        data = {"news": [{"label": "시사", "publisher": "매체", "title": "제목",
                           "url": "https://example.com/article", "published_at": NOW,
                           "detail": "요약 내용"}]}
        before = deepcopy(data)
        with mock.patch.object(rendering.settings, "ENABLED_SECTIONS", {"news"}):
            embeds = rendering.render_sections(NOW, data, compact=True)

        self.assertEqual(data, before)
        self.assertNotIn("요약 내용", embeds[0]["description"])

    def test_optional_only_brief_does_not_report_missing_core_data_as_failure(self):
        for section in ("market", "sports", "study", "community"):
            with self.subTest(section=section):
                embed = rendering.build_header(NOW, {section: {"sample": "available"}}, [])
                self.assertIn("오늘의 관심 소식", embed["description"])
                self.assertNotIn("불러오지 못했습니다", embed["description"])

    def test_empty_successful_notices_are_neutral_but_failed_optional_data_are_not(self):
        empty = rendering.build_header(NOW, {"notices": []}, [])
        failed = rendering.build_header(NOW, {"market": {"sample": "malformed"},
                                             "_render_failed": ["market"]}, ["마켓 표시"])
        weather_failed = rendering.build_header(NOW, {"weather": {"status": "unavailable"}}, ["날씨"])

        self.assertIn("새로 표시할 항목이 없습니다", empty["description"])
        self.assertIn("불러오지 못했습니다", failed["description"])
        self.assertIn("불러오지 못했습니다", weather_failed["description"])


if __name__ == "__main__":
    unittest.main()
