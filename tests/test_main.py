import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import main
from sources._shared import KST, get_failures


NOW = datetime(2026, 9, 11, 7, 30, tzinfo=KST)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 11, 7, 30, tzinfo=tz or KST)


def event(name, start_hour, end_hour, *, all_day=False, location=""):
    return {
        "uid": name,
        "name": name,
        "start": NOW.replace(hour=start_hour, minute=0),
        "end": NOW.replace(hour=end_hour, minute=0),
        "all_day": all_day,
        "location": location,
        "calendar": "테스트 캘린더",
        "transparent": False,
    }


def fresh_weather():
    return {
        "status": "fresh",
        "location": "서울",
        "condition": "비",
        "temperature": 20.0,
        "apparent_temperature": 19.0,
        "low": 17.0,
        "high": 24.0,
        "rain_probability": 80,
        "wind_speed": 10.0,
        "advice": ["우산을 꼭 챙기세요"],
        "as_of": NOW.replace(minute=0),
        "source": "Open-Meteo 예보",
        "source_url": "https://open-meteo.com/en/docs",
    }


def fresh_news(title, published_at):
    return {
        "label": "🌏 국제",
        "title": title,
        "detail": "발행사 리드문",
        "url": f"https://news.example/{title}",
        "publisher": "연합뉴스",
        "published_at": published_at,
        "related": None,
        "summary_kind": "publisher_lead",
        "status": "fresh",
    }


class DeterministicHighlightTests(unittest.TestCase):
    def setUp(self):
        get_failures()

    def tearDown(self):
        get_failures()

    def test_priority_and_active_event_are_deterministic(self):
        data = {
            "schedule": {
                "status": "fresh",
                # Deliberately unsorted to verify selection does not depend on input order.
                "events": [
                    event("나중 일정", 10, 11),
                    event("진행 중 수업", 7, 8, location="미래관"),
                ],
            },
            "assignments": [(-2, "연체 보고서", ""), (0, "오늘 과제", "")],
            "weather": fresh_weather(),
            "news": [fresh_news("최신 기사", NOW - timedelta(minutes=5))],
        }

        first = main._deterministic_highlights(NOW, data)
        second = main._deterministic_highlights(NOW, data)

        self.assertEqual(first, second)
        self.assertEqual(
            [title for title, _detail in first],
            ["연체 과제 1개", "진행 중 · 08:00 종료", "비 · 강수 80%"],
        )
        self.assertIn("미래관", first[1][1])

    def test_latest_news_is_selected_by_timestamp_not_input_order(self):
        older = fresh_news("이전 기사", NOW - timedelta(hours=2))
        newer = fresh_news("최신 기사", NOW - timedelta(minutes=10))
        data = {
            "schedule": {"status": "partial", "events": []},
            "assignments": [],
            "weather": {"status": "unavailable"},
            "news": [older, newer],
        }

        result = main._deterministic_highlights(NOW, data)

        self.assertEqual(result[0][0], "일정 소스 확인 필요")
        self.assertEqual(result[-1], ("최신 시사", "최신 기사 · 연합뉴스 07:20"))

    def test_unconfigured_schedule_is_not_presented_as_empty_verified_calendar(self):
        schedule_data = {
            "status": "unconfigured",
            "events": [],
            "calendar_configured": False,
            "fixed_timetable_used": False,
            "source": "일정 소스 미연결",
        }

        highlights = main._deterministic_highlights(NOW, {"schedule": schedule_data})
        embed = main.build_schedule(schedule_data, [], NOW)

        self.assertEqual(highlights[0][0], "개인 일정 미연결")
        self.assertIn("개인 일정 미연결", embed["description"])
        self.assertNotIn("확인된 오늘 일정 없음", embed["description"])

    def test_build_brief_uses_fixed_section_order_and_source_footers(self):
        data = {
            "weather": fresh_weather(),
            "schedule": {
                "status": "fresh",
                "events": [event("수업", 9, 10)],
                "free_slots": "10:00~23:00",
                "calendar_configured": True,
                "source": "테스트 캘린더",
                "as_of": NOW,
            },
            "assignments": [],
            "news": [fresh_news("기사", NOW - timedelta(minutes=10))],
        }
        with (
            mock.patch.object(main.settings, "ENABLED_SECTIONS", {"news", "schedule", "weather"}),
            mock.patch.object(main, "collect_data", return_value=data),
            mock.patch.object(main, "get_failures", return_value=[]),
        ):
            embeds = main.build_brief(NOW)

        self.assertEqual(
            [embed["title"] for embed in embeds],
            [
                "📰 9월 11일 금요일",
                "🌤️ 오늘 날씨 · 대기질 예보",
                "📅 오늘 일정 · 마감",
                "🗞️ 알아둘 시사",
            ],
        )
        self.assertTrue(all(embed.get("footer", {}).get("text") for embed in embeds))
        self.assertIn("예보 출처", embeds[1]["description"])
        self.assertIn("https://news.example", embeds[3]["description"])


class DeliveryIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self.temp_dir.name, "delivery_state.json")
        self.path_patch = mock.patch.object(main, "DELIVERY_STATE_PATH", self.state_path)
        self.path_patch.start()
        self.wait_patch = mock.patch.object(main, "_wait_until")
        self.wait_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.wait_patch.stop()
        self.temp_dir.cleanup()

    def test_two_scheduled_runs_send_once_after_first_success(self):
        with (
            mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}, clear=True),
            mock.patch.object(main, "datetime", FixedDateTime),
            mock.patch.object(main, "build_brief", return_value=[{"title": "brief"}]) as build,
            mock.patch.object(main.ds, "send") as send,
        ):
            main.main()
            main.main()

        send.assert_called_once_with([{"title": "brief"}])
        build.assert_called_once_with(NOW)
        with open(self.state_path, encoding="utf-8") as state_file:
            state = json.load(state_file)
        self.assertEqual(state["last_successful_date"], "2026-09-11")
        self.assertEqual(state["sent_at"], NOW.isoformat())

    def test_failed_delivery_is_not_marked_successful(self):
        with (
            mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}, clear=True),
            mock.patch.object(main, "datetime", FixedDateTime),
            mock.patch.object(main, "build_brief", return_value=[]),
            mock.patch.object(main.ds, "send", side_effect=RuntimeError("delivery failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "delivery failed"):
                main.main()

        self.assertFalse(os.path.exists(self.state_path))

    def test_manual_run_does_not_treat_scheduled_state_as_a_lock(self):
        with open(self.state_path, "w", encoding="utf-8") as state_file:
            json.dump({"last_successful_date": "2026-09-11"}, state_file)

        with mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch"}, clear=True):
            self.assertFalse(main._scheduled_delivery_done(NOW))

    def test_dry_run_does_not_mark_delivery(self):
        with mock.patch.dict(
            os.environ,
            {"GITHUB_EVENT_NAME": "schedule", "DISCORD_DRY_RUN": "1"},
            clear=True,
        ):
            main._mark_scheduled_delivery(NOW)

        self.assertFalse(os.path.exists(self.state_path))

    def test_valid_json_with_wrong_shape_does_not_crash_duplicate_check(self):
        with open(self.state_path, "w", encoding="utf-8") as state_file:
            json.dump([], state_file)
        with mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}, clear=True):
            self.assertFalse(main._scheduled_delivery_done(NOW))


class ScheduledTimingTests(unittest.TestCase):
    def test_target_is_eight_kst_for_scheduled_runs_only(self):
        with mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}, clear=True):
            self.assertEqual(main._scheduled_target(NOW), NOW.replace(hour=8, minute=0))
            self.assertEqual(main._scheduled_target(NOW.astimezone(timezone.utc)), NOW.replace(hour=8, minute=0))
        for env in ({"GITHUB_EVENT_NAME": "workflow_dispatch"},
                    {"GITHUB_EVENT_NAME": "schedule", "DISCORD_DRY_RUN": "1"},
                    {"GITHUB_EVENT_NAME": "schedule", "BRIEF_READ_ONLY": "1"}):
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertIsNone(main._scheduled_target(NOW))

    def test_wait_rechecks_clock_and_sleeps_in_short_intervals(self):
        target = NOW.replace(hour=8, minute=0)
        times = [target - timedelta(seconds=45), target - timedelta(seconds=15), target]
        with mock.patch.object(main, "datetime") as clock, mock.patch.object(main.time, "sleep") as sleep:
            clock.now.side_effect = times
            main._wait_until(target)
        self.assertEqual(sleep.call_args_list, [mock.call(30), mock.call(15)])

    def test_late_recovery_does_not_wait_until_tomorrow(self):
        target = NOW.replace(hour=8, minute=0)
        with mock.patch.object(main, "datetime") as clock, mock.patch.object(main.time, "sleep") as sleep:
            clock.now.return_value = target + timedelta(minutes=10)
            main._wait_until(target)
        sleep.assert_not_called()

    def test_collection_precedes_eight_but_send_waits_for_eight(self):
        calls = []
        target = NOW.replace(hour=8, minute=0)
        with (mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}, clear=True),
              mock.patch.object(main, "datetime", FixedDateTime),
              mock.patch.object(main, "_scheduled_delivery_done", return_value=False),
              mock.patch.object(main, "_mark_scheduled_delivery"),
              mock.patch.object(main, "_wait_until", side_effect=lambda t: calls.append(t)),
              mock.patch.object(main, "build_brief", side_effect=lambda now: calls.append("collect") or []),
              mock.patch.object(main.ds, "send", side_effect=lambda embeds: calls.append("send")),
              mock.patch.object(main.notices, "commit_pending")):
            main.main()
        self.assertEqual(calls, [target - timedelta(minutes=3), "collect", target, "send"])


if __name__ == "__main__":
    unittest.main()
