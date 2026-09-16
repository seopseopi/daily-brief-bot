import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import settings
from sources import _rss, news
from sources._shared import KST, get_failures


NOW = datetime(2026, 9, 11, 9, 0, tzinfo=KST)


RSS_FIXTURE = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Fixture News</title>
        <item>
          <guid>fixture-1</guid>
          <title><![CDATA[정부 &amp; 대학, AI 예산 발표]]></title>
          <link>https://news.example/article-1</link>
          <description><![CDATA[<p>발행사가 작성한 <b>리드문</b>입니다.</p>]]></description>
          <pubDate>Thu, 10 Sep 2026 23:30:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """
).encode("utf-8")


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


def article(title, published_at, *, link="https://news.example/item", description="발행사 리드문"):
    return {
        "title": title,
        "link": link,
        "description": description,
        "guid": link,
        "published_at": published_at,
        "fetched_at": NOW,
        "source": "Fixture News",
    }


class RssFixtureTests(unittest.TestCase):
    def test_bare_ampersand_in_media_url_does_not_drop_entire_feed(self):
        raw = RSS_FIXTURE.replace(b'<item>', b'<item><media url="https://example.com/watch?v=1&feature=share"/>')
        with mock.patch.object(_rss, "open_url", return_value=FakeResponse(raw)):
            items = _rss.fetch_rss("https://news.example/rss")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "정부 & 대학, AI 예산 발표")
        self.assertEqual(items[0]["link"], "https://news.example/article-1")

    def test_malformed_xml_still_raises_instead_of_claiming_empty_feed(self):
        with mock.patch.object(_rss, "open_url", return_value=FakeResponse(b'<rss><channel>')):
            with self.assertRaises(_rss.ET.ParseError):
                _rss.fetch_rss("https://news.example/rss")

    def test_rss_preserves_source_timestamp_and_cleans_publisher_lead(self):
        with mock.patch.object(
            _rss.urllib.request,
            "urlopen",
            return_value=FakeResponse(RSS_FIXTURE),
        ) as urlopen:
            items = _rss.fetch_rss("https://news.example/feed.xml")

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["source"], "Fixture News")
        self.assertEqual(item["guid"], "fixture-1")
        self.assertEqual(item["title"], "정부 & 대학, AI 예산 발표")
        self.assertEqual(item["description"], "발행사가 작성한 리드문 입니다.")
        self.assertEqual(item["published_at"], datetime(2026, 9, 10, 23, 30, tzinfo=timezone.utc))
        self.assertIsNotNone(item["fetched_at"].tzinfo)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], _rss.TIMEOUT)

    def test_iso_and_rfc_dates_are_timezone_aware(self):
        iso = _rss.parse_datetime("2026-09-11T08:30:00+09:00")
        rfc = _rss.parse_datetime("Thu, 10 Sep 2026 23:30:00 GMT")

        self.assertEqual(iso.utcoffset(), timedelta(hours=9))
        self.assertEqual(rfc.tzinfo, timezone.utc)
        self.assertIsNone(_rss.parse_datetime("not a date"))


class NewsFreshnessTests(unittest.TestCase):
    def setUp(self):
        get_failures()

    def tearDown(self):
        get_failures()

    def test_failed_primary_uses_fresh_fallback_with_actual_publisher(self):
        def feed(url):
            if url == news.YONHAP_POLITICS:
                raise _rss.ET.ParseError("broken feed")
            return [article("대체 기사", NOW - timedelta(minutes=5))]
        with (mock.patch.object(news, "CATEGORIES", (("🏛️ 정치", news.YONHAP_POLITICS, "연합뉴스"),)),
              mock.patch.object(_rss, "fetch_rss", side_effect=feed),
              mock.patch.object(settings, "USE_LLM_NEWS_SUMMARIES", False)):
            result = news.get_news(NOW)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["publisher"], "한국경제")
        self.assertIsNone(result[0]["related"])
        self.assertEqual(get_failures(), [])

    def test_freshness_rejects_old_missing_and_far_future_articles(self):
        fixtures = [
            article("old", NOW - timedelta(hours=24, seconds=1)),
            article("missing", None),
            article("future", NOW + timedelta(minutes=21)),
            article("boundary old", NOW - timedelta(hours=24)),
            article("boundary future", NOW + timedelta(minutes=20)),
            article("newest", NOW - timedelta(minutes=5)),
        ]

        with mock.patch.object(settings, "NEWS_MAX_AGE_HOURS", 24):
            result = news._fresh(fixtures, NOW)

        self.assertEqual(
            [item["title"] for item in result],
            ["boundary future", "newest", "boundary old"],
        )
        self.assertTrue(all(item["published_at"].tzinfo == KST for item in result))

    def test_get_news_selects_freshest_per_category_without_llm(self):
        stale = article("오래된 기사", NOW - timedelta(hours=30))

        def feed_fixture(url):
            if url == news.HANKYUNG_POLITICS:
                return [
                    article(
                        "정부 AI 예산 확대 계획 공개",
                        NOW - timedelta(minutes=20),
                        link="https://hankyung.example/politics-related",
                    )
                ]
            if url == news.YONHAP_POLITICS:
                fresh = article(
                    "정부 AI 예산 확대 발표",
                    NOW - timedelta(minutes=10),
                    link="https://yonhap.example/politics",
                )
            else:
                label = next(label for label, feed_url, _publisher in news.CATEGORIES if feed_url == url)
                fresh = article(
                    f"{label} 최신 기사",
                    NOW - timedelta(minutes=30),
                    link=f"https://news.example/{label}",
                )
            # Feed order is intentionally stale-first: selection must use time.
            return [stale, fresh]

        with (
            mock.patch.object(settings, "NEWS_MAX_AGE_HOURS", 24),
            mock.patch.object(settings, "USE_LLM_NEWS_SUMMARIES", False),
            mock.patch.object(_rss, "fetch_rss", side_effect=feed_fixture),
            mock.patch.object(news._llm, "explain_news") as llm,
        ):
            result = news.get_news(NOW)

        llm.assert_not_called()
        self.assertEqual(len(result), len(news.CATEGORIES))
        self.assertTrue(all(item["status"] == "fresh" for item in result))
        self.assertTrue(all(item["title"] != "오래된 기사" for item in result))
        politics = result[0]
        self.assertEqual(politics["summary_kind"], "publisher_lead")
        self.assertEqual(politics["related"]["publisher"], "한국경제")
        self.assertEqual(politics["related"]["url"], "https://hankyung.example/politics-related")

    def test_category_with_only_stale_articles_is_omitted_and_reported(self):
        with (
            mock.patch.object(settings, "NEWS_MAX_AGE_HOURS", 24),
            mock.patch.object(settings, "USE_LLM_NEWS_SUMMARIES", False),
            mock.patch.object(
                _rss,
                "fetch_rss",
                return_value=[article("오래된 기사", NOW - timedelta(hours=25))],
            ),
        ):
            result = news.get_news(NOW)

        self.assertEqual(result, [])
        failures = get_failures()
        self.assertEqual(len([failure for failure in failures if failure.startswith("뉴스-")]), len(news.CATEGORIES))


if __name__ == "__main__":
    unittest.main()
