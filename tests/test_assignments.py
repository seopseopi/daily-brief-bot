import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from sources import assignments


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 11, 7, 13, tzinfo=tz)


class AssignmentTests(unittest.TestCase):
    def test_history_resolves_relative_deadlines_from_each_message_kst_date(self):
        messages = [
            {"id": "1", "content": "내일까지 첫 과제", "timestamp": "2026-09-08T16:00:00Z"},
            {"id": "2", "content": "내일까지 둘째 과제", "timestamp": "2026-09-09T16:00:00Z"},
            {"id": "3", "content": "완료 | 첫 과제", "timestamp": "2026-09-10T01:00:00Z"},
        ]
        def parse(contents, message_date):
            deadline = (datetime.fromisoformat(message_date) + timedelta(days=1)).date().isoformat()
            return [{"action": "add", "name": content.split("내일까지 ")[1],
                     "deadline": deadline, "note": ""} for content in contents]
        with (mock.patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "token", "ASSIGNMENT_CHANNEL_ID": "123"}, clear=True),
              mock.patch.object(assignments, "datetime", FixedDateTime),
              mock.patch.object(assignments._discord, "fetch_channel_history", return_value=messages),
              mock.patch.object(assignments._llm, "parse_assignments", side_effect=parse) as parser):
            result = assignments._fetch_discord_assignments()
        self.assertEqual([c.args[1] for c in parser.call_args_list], ["2026-09-09", "2026-09-10"])
        self.assertEqual([(item["name"], item["deadline"]) for item in result], [("둘째 과제", "2026-09-11")])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self.temp_dir.name, "discord_assignments.json")
        self.path_patch = mock.patch.object(assignments, "DISCORD_ASSIGNMENTS_PATH", self.state_path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def save_state(self, state):
        assignments._save_state(state)

    def read_state(self):
        with open(self.state_path, encoding="utf-8") as file:
            return json.load(file)

    def test_missing_credentials_returns_saved_assignments(self):
        cached = [{"message_id": "1", "deadline": "2026-09-14", "name": "알고리즘", "note": ""}]
        self.save_state({"last_message_id": "1", "assignments": cached})

        with mock.patch.dict(os.environ, {}, clear=True):
            result = assignments._fetch_discord_assignments()

        self.assertEqual(result, cached)
        self.assertEqual(self.read_state()["last_message_id"], "1")

    def test_discord_fetch_failure_returns_saved_assignments(self):
        cached = [{"message_id": "1", "deadline": "2026-09-14", "name": "알고리즘", "note": ""}]
        self.save_state({"last_message_id": "1", "assignments": cached})

        with (
            mock.patch.dict(
                os.environ,
                {"DISCORD_BOT_TOKEN": "token", "ASSIGNMENT_CHANNEL_ID": "channel"},
                clear=True,
            ),
            mock.patch.object(assignments._discord, "fetch_channel_messages", side_effect=OSError("offline")),
        ):
            result = assignments._fetch_discord_assignments()

        self.assertEqual(result, cached)
        self.assertEqual(self.read_state()["last_message_id"], "1")

    def test_fresh_runner_rebuilds_state_from_discord_history(self):
        messages = [{
            "id": "11",
            "content": "추가 | 2026-09-15 | 데이터과학 보고서 | PDF 제출",
            "author": {"bot": False},
        }]
        with (
            mock.patch.dict(
                os.environ,
                {"DISCORD_BOT_TOKEN": "token", "ASSIGNMENT_CHANNEL_ID": "123"},
                clear=True,
            ),
            mock.patch.object(assignments._discord, "fetch_channel_history", return_value=messages) as history,
            mock.patch.object(assignments._discord, "fetch_channel_messages") as incremental,
        ):
            result = assignments._fetch_discord_assignments()

        history.assert_called_once()
        incremental.assert_not_called()
        self.assertEqual([item["name"] for item in result], ["데이터과학 보고서"])
        self.assertEqual(self.read_state()["last_message_id"], "11")

    def test_explicit_add_with_time_is_deterministic(self):
        self.save_state({"last_message_id": "10", "assignments": []})
        messages = [{
            "id": "11",
            "content": "추가 | 2026-09-15 23:59 | 데이터과학 보고서 | PDF 제출",
            "author": {"bot": False},
        }]

        with (
            mock.patch.dict(
                os.environ,
                {"DISCORD_BOT_TOKEN": "token", "ASSIGNMENT_CHANNEL_ID": "channel"},
                clear=True,
            ),
            mock.patch.object(assignments._discord, "fetch_channel_messages", return_value=messages),
            mock.patch.object(assignments._llm, "parse_assignments") as parse_llm,
        ):
            result = assignments._fetch_discord_assignments()

        parse_llm.assert_not_called()
        self.assertEqual(result[0]["deadline"], "2026-09-15")
        self.assertEqual(result[0]["deadline_time"], "23:59")
        self.assertEqual(result[0]["name"], "데이터과학 보고서")
        self.assertEqual(self.read_state()["last_message_id"], "11")

    def test_llm_failure_does_not_advance_cursor(self):
        self.save_state({"last_message_id": "10", "assignments": []})
        messages = [
            {
                "id": "11",
                "content": "추가 | 2026-09-15 | 알고리즘 과제 |",
                "author": {"bot": False},
            },
            {"id": "12", "content": "다음 주까지 보고서", "author": {"bot": False}},
        ]

        with (
            mock.patch.dict(
                os.environ,
                {"DISCORD_BOT_TOKEN": "token", "ASSIGNMENT_CHANNEL_ID": "channel"},
                clear=True,
            ),
            mock.patch.object(assignments._discord, "fetch_channel_messages", return_value=messages),
            mock.patch.object(assignments._llm, "parse_assignments", side_effect=RuntimeError("LLM down")),
        ):
            result = assignments._fetch_discord_assignments()

        state = self.read_state()
        self.assertEqual(state["last_message_id"], "10")
        self.assertEqual([item["name"] for item in result], ["알고리즘 과제"])
        self.assertEqual(state["assignments"], result)

    def test_explicit_completion_requires_exact_name(self):
        cached = [
            {"message_id": "1", "deadline": "2026-09-15", "name": "알고리즘 과제 1", "note": ""},
            {"message_id": "2", "deadline": "2026-09-16", "name": "알고리즘 과제 2", "note": ""},
        ]
        messages = [{"id": "3", "content": "완료 | 알고리즘 과제", "author": {"bot": False}}]
        self.save_state({"last_message_id": "2", "assignments": cached})

        with (
            mock.patch.dict(
                os.environ,
                {"DISCORD_BOT_TOKEN": "token", "ASSIGNMENT_CHANNEL_ID": "channel"},
                clear=True,
            ),
            mock.patch.object(assignments._discord, "fetch_channel_messages", return_value=messages),
            mock.patch.object(assignments._llm, "parse_assignments") as parse_llm,
        ):
            result = assignments._fetch_discord_assignments()

        parse_llm.assert_not_called()
        self.assertEqual(result, cached)
        self.assertEqual(self.read_state()["last_message_id"], "3")

    def test_ambiguous_partial_llm_completion_does_not_delete(self):
        cached = [
            {"deadline": "2026-09-15", "name": "알고리즘 과제 1"},
            {"deadline": "2026-09-16", "name": "알고리즘 과제 2"},
        ]

        result = assignments._remove_matching(cached, "알고리즘 과제")

        self.assertEqual(result, cached)

    def test_unique_partial_llm_completion_remains_compatible(self):
        cached = [
            {"deadline": "2026-09-15", "name": "알고리즘 과제"},
            {"deadline": "2026-09-16", "name": "데이터과학 보고서"},
        ]

        result = assignments._remove_matching(cached, "알고리즘")

        self.assertEqual([item["name"] for item in result], ["데이터과학 보고서"])

    def test_overdue_assignments_are_returned_as_negative_days(self):
        cached = [{
            "message_id": "1",
            "deadline": "2026-09-09",
            "deadline_time": "18:00",
            "name": "연체 보고서",
            "note": "제출",
        }]
        with (
            mock.patch.object(assignments, "datetime", FixedDateTime),
            mock.patch.object(assignments, "ASSIGNMENTS", [("2026-09-10", "수동 연체", "")]),
            mock.patch.object(assignments, "_fetch_discord_assignments", return_value=cached),
        ):
            result = assignments.get_assignments()

        self.assertIn((-1, "수동 연체", ""), result)
        self.assertIn((-2, "연체 보고서", "18:00 마감 · 제출"), result)

    def test_invalid_explicit_date_is_rejected(self):
        with self.assertRaises(ValueError):
            assignments._parse_explicit_message("추가 | 2026-02-30 | 과제 | 메모")

    def test_one_malformed_explicit_message_does_not_block_other_commands(self):
        messages = [
            {
                "id": "11",
                "content": "추가 | 2026-09-15 | 첫 과제 |",
                "author": {"bot": False},
            },
            {
                "id": "12",
                "content": "추가 | 2026-02-30 | 잘못된 과제 |",
                "author": {"bot": False},
            },
            {
                "id": "13",
                "content": "추가 | 2026-09-17 | 둘째 과제 |",
                "author": {"bot": False},
            },
        ]
        with (
            mock.patch.dict(
                os.environ,
                {"DISCORD_BOT_TOKEN": "token", "ASSIGNMENT_CHANNEL_ID": "123"},
                clear=True,
            ),
            mock.patch.object(assignments._discord, "fetch_channel_history", return_value=messages),
        ):
            result = assignments._fetch_discord_assignments()

        self.assertEqual([item["name"] for item in result], ["첫 과제", "둘째 과제"])
        self.assertEqual(self.read_state()["last_message_id"], "13")

    def test_large_natural_language_history_is_parsed_in_bounded_batches(self):
        messages = [
            {"id": str(index), "content": f"자연어 메시지 {index}", "author": {"bot": False}}
            for index in range(1, 22)
        ]

        def parse_batch(contents, _today):
            return [None] * len(contents)

        with (
            mock.patch.dict(
                os.environ,
                {"DISCORD_BOT_TOKEN": "token", "ASSIGNMENT_CHANNEL_ID": "123"},
                clear=True,
            ),
            mock.patch.object(assignments._discord, "fetch_channel_history", return_value=messages),
            mock.patch.object(assignments._llm, "parse_assignments", side_effect=parse_batch) as parser,
        ):
            result = assignments._fetch_discord_assignments()

        self.assertEqual(result, [])
        self.assertEqual([len(call.args[0]) for call in parser.call_args_list], [10, 10, 1])
        self.assertEqual(self.read_state()["last_message_id"], "21")


if __name__ == "__main__":
    unittest.main()
