import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from sources import _community, community


NOW = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)


class CommunitySourceTests(unittest.TestCase):
    def test_dc_filters_old_posts_and_preserves_metadata(self):
        page = """
        <tr class="ub-content us-post" data-no="1" data-type="icon_txt">
          <td class="gall_tit ub-word"><a href="/view/1">오래된 인기글</a><span>[30]</span></td>
          <td class="gall_date" title="2026-09-09 08:00:00">09.09</td>
          <td class="gall_count">9999</td>
        <tr class="ub-content us-post" data-no="2" data-type="icon_txt">
          <td class="gall_tit ub-word"><a href="/view/2">최신 정보글</a><span>[7]</span></td>
          <td class="gall_date" title="2026-09-11 08:30:00">08:30</td>
          <td class="gall_count">321</td>
        """.encode()

        with mock.patch.object(_community, "_get", return_value=page):
            post = _community.fetch_dc_top_post("chatgpt", now=NOW)

        self.assertEqual(post["title"], "최신 정보글")
        self.assertEqual(post["views"], 321)
        self.assertEqual(post["comments"], 7)
        self.assertIsNone(post["score"])
        self.assertEqual(post["published_at"].tzinfo, timezone.utc)
        self.assertEqual(post["signal_type"], "반응 신호")

    def test_reddit_uses_published_time_and_marks_unavailable_metrics(self):
        feed = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Fresh model discussion</title>
            <published>2026-09-10T23:00:00+00:00</published>
            <link href="https://reddit.example/post" />
            <content type="html">&lt;p&gt;Measured results from the poster.&lt;/p&gt;</content>
          </entry>
        </feed>""".encode()

        with mock.patch.object(_community, "_get", return_value=feed):
            post = _community.fetch_reddit_top_post("LocalLLaMA", now=NOW)

        self.assertEqual(post["published_at"], NOW - timedelta(hours=1))
        self.assertIsNone(post["score"])
        self.assertIsNone(post["comments"])
        self.assertEqual(post["excerpt"], "Measured results from the poster.")
        self.assertEqual(post["source_kind"], "reddit")

    def test_hn_official_api_skips_stale_story_and_keeps_engagement(self):
        old_time = int((NOW - timedelta(hours=30)).timestamp())
        fresh_time = int((NOW - timedelta(hours=2)).timestamp())
        responses = {
            f"{_community.HN_API_BASE}/topstories.json": [1, 2],
            f"{_community.HN_API_BASE}/item/1.json": {
                "id": 1, "type": "story", "title": "Old", "time": old_time,
                "score": 999, "descendants": 50,
            },
            f"{_community.HN_API_BASE}/item/2.json": {
                "id": 2, "type": "story", "title": "Fresh", "time": fresh_time,
                "score": 123, "descendants": 45, "url": "https://example.com/article",
            },
        }

        def fake_get(url):
            return json.dumps(responses[url]).encode()

        with mock.patch.object(_community, "_get", side_effect=fake_get):
            post = _community.fetch_hn_top_post(now=NOW)

        self.assertEqual(post["title"], "Fresh")
        self.assertEqual(post["score"], 123)
        self.assertEqual(post["comments"], 45)
        self.assertEqual(post["published_at"], NOW - timedelta(hours=2))
        self.assertEqual(post["signal_type"], "정보 링크")
        self.assertIn("news.ycombinator.com/item?id=2", post["discussion_url"])

    def test_missing_timestamp_is_not_assumed_fresh(self):
        self.assertFalse(_community.is_fresh(None, now=NOW))
        self.assertFalse(_community.is_fresh(NOW - timedelta(hours=25), now=NOW))
        self.assertTrue(_community.is_fresh(NOW - timedelta(hours=24), now=NOW))


class CommunityPresentationTests(unittest.TestCase):
    @staticmethod
    def _post(kind, title, *, signal="반응 신호", excerpt="본문", score=None,
              comments=3, views=None):
        return {
            "source_kind": kind,
            "signal_type": signal,
            "title": title,
            "url": f"https://example.com/{kind}/{title}",
            "published_at": NOW - timedelta(hours=1),
            "score": score,
            "comments": comments,
            "views": views,
            "excerpt": excerpt,
        }

    def test_output_keeps_five_tuple_contract_and_source_diversity(self):
        dc = self._post("dc", "DC", views=200)
        reddit = self._post("reddit", "Reddit", comments=None)
        hn = self._post(
            "hn", "HN", signal="정보 링크", excerpt="", score=80, comments=12,
        )

        with (
            mock.patch.object(_community, "fetch_dc_top_post", return_value=dc),
            mock.patch.object(_community, "fetch_reddit_top_post", return_value=reddit),
            mock.patch.object(_community, "fetch_hn_top_post", return_value=hn),
            mock.patch.object(community, "_dc_excerpt_raw", return_value="DC 원문 발췌"),
            mock.patch.object(community, "tr", side_effect=lambda text, cap=None: text),
            mock.patch.object(_community, "fetch_dc_post_excerpt", return_value="DC 원문 발췌"),
            mock.patch.object(_community, "is_fresh", return_value=True),
            mock.patch.object(community._llm, "explain_community", side_effect=lambda items: ["요약"] * len(items)),
        ):
            result = community.get_community(now=NOW)

        self.assertEqual(len(result), community.MAX_ITEMS)
        self.assertTrue(all(len(item) == 5 for item in result))
        first_three_labels = [item[0] for item in result[:3]]
        self.assertTrue(any("Hacker News" in label for label in first_three_labels))
        self.assertTrue(any("r/" in label for label in first_three_labels))
        self.assertTrue(any("갤" in label for label in first_three_labels))
        self.assertTrue(all("게시 " in item[1] for item in result))
        self.assertTrue(all("미검증" in item[3] or "사실 확인 필요" in item[3] for item in result))

    def test_invalid_environment_freshness_falls_back_to_24_hours(self):
        with mock.patch.dict(os.environ, {"COMMUNITY_MAX_AGE_HOURS": "invalid"}):
            self.assertEqual(community._resolve_max_age_hours(), 24.0)

    def test_llm_failure_keeps_unverified_excerpt_fallback(self):
        groups = {
            "hn": [],
            "reddit": [("r/Test", self._post("reddit", "제목", excerpt="원문 발췌", comments=None))],
            "dc": [],
        }
        with (
            mock.patch.object(community, "_collect", return_value=groups),
            mock.patch.object(community, "tr", side_effect=lambda text, cap=None: text),
            mock.patch.object(community._llm, "explain_community", side_effect=RuntimeError("down")),
        ):
            result = community.get_community(now=NOW)

        self.assertIn("원문 발췌", result[0][3])
        self.assertIn("사실 확인 필요", result[0][3])


if __name__ == "__main__":
    unittest.main()
