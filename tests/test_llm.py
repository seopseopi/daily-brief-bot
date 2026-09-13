import copy
import json
import unittest
from datetime import datetime
from unittest import mock

import settings
from sources import _llm, assignments, news, study
from sources._shared import KST, get_failures


PAPER = {
    "problem": "문제",
    "method": "방법",
    "result": "결과",
    "limitation": "초록에 명시된 한계 없음",
    "connection": "직접적 접점 없음",
}
GLOSSARY = {
    "concept": {"name": "개념", "desc": "개념 설명"},
    "terms": [{"term": f"용어 {i}", "desc": "용어 설명"} for i in range(3)],
}


class LlmSchemaTests(unittest.TestCase):
    def test_news_and_community_reject_same_length_objects_and_invalid_text(self):
        inputs = [{"label": "소스", "title": "제목", "lead": "리드", "excerpt": "발췌"}]
        for function in (_llm.explain_news, _llm.explain_community):
            for response in ({"private-source-text": "설명"}, "가", None, [], [0], [False], [{}], [None], [""], [" \n"]):
                with self.subTest(function=function.__name__, response=response):
                    with mock.patch.object(_llm, "_call_json", return_value=response):
                        with self.assertRaises(ValueError) as raised:
                            function(inputs)
                    self.assertNotIn("private-source-text", str(raised.exception))

    def test_valid_text_preserves_order_and_trims_surrounding_whitespace(self):
        inputs = [{"label": "소스", "title": "제목", "lead": "리드", "excerpt": "발췌"}] * 2
        for function in (_llm.explain_news, _llm.explain_community):
            with self.subTest(function=function.__name__):
                with mock.patch.object(_llm, "_call_json", return_value=[" 첫 설명 ", "둘째 설명\n"]):
                    self.assertEqual(function(inputs), ["첫 설명", "둘째 설명"])

    def test_paper_requires_all_five_nonempty_text_sections(self):
        for response in ([], None, {}, {**PAPER, "result": []}, {**PAPER, "method": " "}):
            with self.subTest(response=response):
                with mock.patch.object(_llm, "_call_json", return_value=response):
                    with self.assertRaises(ValueError):
                        _llm.summarize_paper("제목", "초록", "분야", ["키워드"])

    def test_paper_returns_only_documented_fields(self):
        with mock.patch.object(_llm, "_call_json", return_value={**PAPER, "extra": {"text": "untrusted"}}):
            self.assertEqual(_llm.summarize_paper("제목", "초록", "분야", []), PAPER)

    def test_glossary_rejects_invalid_nested_fields_and_wrong_term_count(self):
        invalid = [[], None, {}, {**GLOSSARY, "concept": "개념"}, {**GLOSSARY, "terms": {}}]
        for field, value in (("concept", {"name": "개념", "desc": 3}), ("terms", GLOSSARY["terms"][:2]), ("terms", [{"term": "", "desc": "설명"}] * 3)):
            invalid.append({**GLOSSARY, field: value})
        for response in invalid:
            with self.subTest(response=response):
                with mock.patch.object(_llm, "_call_json", return_value=response):
                    with self.assertRaises(ValueError):
                        _llm.generate_glossary("제목", "초록")

    def test_glossary_preserves_valid_structure_and_drops_unknown_keys(self):
        response = copy.deepcopy(GLOSSARY)
        response["concept"]["extra"] = "ignored"
        response["terms"][0]["extra"] = "ignored"
        with mock.patch.object(_llm, "_call_json", return_value=response):
            self.assertEqual(_llm.generate_glossary("제목", "초록"), GLOSSARY)

    def test_highlights_require_exactly_three_valid_title_reason_pairs(self):
        valid = [{"title": "제목", "reason": "이유"}] * 3
        for response in ({"one": {}, "two": {}, "three": {}}, valid[:2], valid + valid[:1], [*valid[:2], {"title": [], "reason": "이유"}]):
            with self.subTest(response=response):
                with mock.patch.object(_llm, "_call_json", return_value=response):
                    with self.assertRaises(ValueError):
                        _llm.summarize_highlights("본문")
        with mock.patch.object(_llm, "_call_json", return_value=valid):
            self.assertEqual(_llm.summarize_highlights("본문"), [("제목", "이유")] * 3)

    def test_assignment_rejects_wrong_container_count_and_action_shapes(self):
        malformed_items = [
            False, "null", [], {}, {"action": "delete"}, {"action": "add"},
            {"action": "add", "name": "과제", "deadline": 20260920},
            {"action": "add", "name": " ", "deadline": "2026-09-20"},
            {"action": "add", "name": "과제", "deadline": "2026-09-20", "note": []},
            {"action": "add", "name": "과제", "deadline": "2026-09-20", "deadline_time": 12},
            {"action": "complete", "name_hint": " "},
        ]
        for response in ({"null": None}, "x", [], [None, None], *([item] for item in malformed_items)):
            with self.subTest(response=response):
                with mock.patch.object(_llm, "_call_json", return_value=response):
                    with self.assertRaises(ValueError):
                        _llm.parse_assignments(["과제 메시지"], "2026-09-13")

    def test_assignment_keeps_null_and_optional_time_but_drops_internal_control_keys(self):
        response = [
            {"action": "add", "name": " 과제 ", "deadline": "2026-09-20", "deadline_time": "12:00", "_explicit": True},
            {"action": "complete", "name_hint": " 과제 ", "_explicit": True},
            None,
        ]
        with mock.patch.object(_llm, "_call_json", return_value=response):
            parsed = _llm.parse_assignments(["추가", "완료", "잡담"], "2026-09-13")
        self.assertEqual(parsed, [
            {"action": "add", "name": "과제", "deadline": "2026-09-20", "note": "", "deadline_time": "12:00"},
            {"action": "complete", "name_hint": "과제"},
            None,
        ])
        self.assertIn("_explicit", response[0])  # Validation does not mutate the raw response.

    def test_assignment_calendar_validation_remains_in_apply_layer(self):
        response = [{"action": "add", "name": "과제", "deadline": "2026-02-30"}]
        with mock.patch.object(_llm, "_call_json", return_value=response):
            parsed = _llm.parse_assignments(["과제"], "2026-09-13")
        with self.assertRaises(ValueError):
            assignments._apply_parsed([], [{"id": "1"}], parsed)

    def test_json_parser_marks_source_content_as_data(self):
        with mock.patch.object(_llm, "_call", return_value='["요약"]') as call:
            self.assertEqual(_llm._call_json("원문", max_tokens=123), ["요약"])
        self.assertTrue(call.call_args.args[0].startswith(_llm.SOURCE_DATA_INSTRUCTION))
        self.assertEqual(call.call_args.args[1], 123)


class LlmFallbackTests(unittest.TestCase):
    def setUp(self):
        get_failures()

    def tearDown(self):
        get_failures()

    def test_invalid_news_json_preserves_publisher_lead(self):
        article = {
            "label": "기술", "title": "제목", "detail": "발행사 원문 리드", "url": "https://example.com/news",
            "publisher": "발행사", "summary_kind": "publisher_lead", "status": "fresh",
        }
        with (
            mock.patch.object(settings, "USE_LLM_NEWS_SUMMARIES", True),
            mock.patch.object(news, "CATEGORIES", [("기술", "https://example.com/rss", "발행사")]),
            mock.patch.object(news, "_read_category", return_value=article),
            mock.patch.object(_llm, "_call", return_value=json.dumps({"wrong": "형식"})),
        ):
            result = news.get_news(datetime(2026, 9, 13, 7, tzinfo=KST))
        self.assertEqual(result[0]["detail"], "발행사 원문 리드")
        self.assertEqual(result[0]["summary_kind"], "publisher_lead")
        self.assertIn("뉴스 요약(LLM)", get_failures())

    def test_invalid_glossary_is_omitted_at_existing_fallback(self):
        with mock.patch.object(_llm, "_call", return_value=json.dumps({**GLOSSARY, "concept": {"name": "개념", "desc": []}})):
            self.assertEqual(study._glossary({"title": "제목", "summary": "초록"}), (None, []))
        self.assertIn("개념·용어(LLM)", get_failures())

    def test_invalid_assignment_batch_keeps_cursor_and_applies_explicit_command(self):
        state = {"last_message_id": "10", "assignments": []}
        messages = [
            {"id": "11", "content": "추가 | 2026-09-20 | 명시적 과제"},
            {"id": "12", "content": "다음 주까지 자연어 과제"},
        ]
        with (
            mock.patch.dict("os.environ", {"DISCORD_BOT_TOKEN": "test-token", "ASSIGNMENT_CHANNEL_ID": "test-channel"}),
            mock.patch.object(assignments, "_load_state", return_value=state),
            mock.patch.object(assignments, "_save_state") as save,
            mock.patch.object(assignments._discord, "fetch_channel_messages", return_value=messages),
            mock.patch.object(_llm, "_call", return_value="[false]"),
        ):
            result = assignments._fetch_discord_assignments()
        self.assertEqual([item["name"] for item in result], ["명시적 과제"])
        self.assertEqual(save.call_args.args[0]["last_message_id"], "10")
        self.assertIn("과제 자동파싱(LLM)", get_failures())


if __name__ == "__main__":
    unittest.main()
