import unittest
import urllib.error
from datetime import datetime, timezone
from unittest import mock

from sources import _arxiv


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def feed(*entries):
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:arxiv="http://arxiv.org/schemas/atom" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<updated>2026-09-14T05:00:00Z</updated>'
        + "".join(entries) + "</feed>"
    ).encode()


def announcement(paper_id="2609.12345", *, kind="new", published="2026-09-14T00:00:00-04:00", abstract="We evaluate a vision-language model.", title="Paper title"):
    return f"""<entry>
      <id>oai:arXiv.org:{paper_id}v1</id><title>{title}</title>
      <updated>2026-09-14T05:00:00Z</updated>
      <link href="https://arxiv.org/abs/{paper_id}" rel="alternate" type="text/html"/>
      <summary>arXiv:{paper_id}v1 Announce Type: {kind}
        Abstract: {abstract}</summary>
      <published>{published}</published><arxiv:announce_type>{kind}</arxiv:announce_type>
      <dc:creator>Alice Author, Bob Author</dc:creator>
    </entry>"""


API_FEED = feed("""<entry>
  <id>http://arxiv.org/abs/2609.12345v1</id><title> Paper\n title </title>
  <summary>We evaluate a vision language model.</summary>
  <published>2026-09-13T10:00:00Z</published><updated>2026-09-13T10:00:00Z</updated>
  <author><name>Alice Author</name></author>
</entry>""")


class ArxivConnectionTests(unittest.TestCase):
    def test_working_api_preserves_dates_authors_and_uses_one_request(self):
        with mock.patch.object(_arxiv.urllib.request, "urlopen", return_value=Response(API_FEED)) as request:
            papers = _arxiv.search(["vision language model"], ["cs.CV"], max_results=10)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(papers[0]["title"], "Paper title")
        self.assertEqual(papers[0]["url"], "https://arxiv.org/abs/2609.12345v1")
        self.assertEqual(papers[0]["authors"], ["Alice Author"])
        self.assertEqual(papers[0]["published_at"], datetime(2026, 9, 13, 10, tzinfo=timezone.utc))
        self.assertEqual(papers[0]["date_kind"], "submitted")

    def test_rate_limit_switches_once_to_official_category_feed_without_retry(self):
        rate_limit = urllib.error.HTTPError("https://export.arxiv.org/api/query", 429, "Rate exceeded", {}, None)
        with (
            mock.patch.object(_arxiv.urllib.request, "urlopen", side_effect=[rate_limit, Response(feed(announcement()))]) as request,
            mock.patch.object(_arxiv.time, "sleep") as sleep,
        ):
            papers = _arxiv.search(["vision language model"], ["cs.CV", "cs.CL", "cs.CV"], max_results=10)
        self.assertEqual(request.call_count, 2)
        sleep.assert_not_called()
        self.assertEqual(request.call_args_list[1].args[0].full_url, "https://rss.arxiv.org/atom/cs.CV+cs.CL")
        self.assertEqual(request.call_args_list[1].kwargs["timeout"], _arxiv.RSS_TIMEOUT)
        self.assertEqual(papers[0]["summary"], "We evaluate a vision-language model.")
        self.assertEqual(papers[0]["authors"], ["Alice Author", "Bob Author"])
        self.assertEqual(papers[0]["date_kind"], "announcement")
        self.assertEqual(papers[0]["published_at"], datetime(2026, 9, 14, 4, tzinfo=timezone.utc))
        self.assertIsNone(papers[0]["updated_at"])

    def test_new_feed_filters_updates_missing_dates_and_unrelated_papers_before_limit(self):
        entries = feed(
            announcement("2609.10000", abstract="Unrelated network dynamics."),
            announcement("2609.10001", kind="replace"),
            announcement("2609.10002", kind="cross"),
            announcement("2609.10003", kind="replace-cross"),
            announcement("2609.10004", published=""),
            announcement("2609.10005", published="2026-09-14T00:00:00"),
            announcement("2609.10006", published="2026-09-11T00:00:00-04:00"),
            announcement("2609.10007"),
            announcement("2609.10007"),
        )
        with mock.patch.object(_arxiv.urllib.request, "urlopen", return_value=Response(entries)):
            papers = _arxiv._search_announcements(["vision language model"], ["cs.CV"], 1)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["url"], "https://arxiv.org/abs/2609.10007")

    def test_no_keyword_match_returns_empty_without_unrelated_substitution(self):
        with mock.patch.object(_arxiv.urllib.request, "urlopen", return_value=Response(feed(announcement(abstract="Network dynamics.")))):
            self.assertEqual(_arxiv._search_announcements(["hallucination"], ["cs.CV"], 10), [])

    def test_persistent_timeout_has_bounded_retry_then_one_feed_request(self):
        with (
            mock.patch.object(_arxiv.urllib.request, "urlopen", side_effect=[TimeoutError(), TimeoutError(), Response(feed(announcement()))]) as request,
            mock.patch.object(_arxiv.time, "sleep") as sleep,
        ):
            papers = _arxiv.search(["vision language model"], ["cs.CV"])
        self.assertEqual(request.call_count, _arxiv.RETRIES + 1)
        sleep.assert_called_once_with(_arxiv.RETRY_BACKOFF)
        self.assertEqual(len(papers), 1)

    def test_invalid_query_is_reported_without_retry_or_category_fallback(self):
        error = urllib.error.HTTPError("https://export.arxiv.org/api/query", 400, "Invalid query", {}, None)
        with (
            mock.patch.object(_arxiv.urllib.request, "urlopen", side_effect=error) as request,
            mock.patch.object(_arxiv.time, "sleep") as sleep,
        ):
            with self.assertRaises(urllib.error.HTTPError):
                _arxiv.search(["keyword"], ["cs.CV"])
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_feed_failure_remains_an_error_instead_of_claiming_no_papers(self):
        error = urllib.error.HTTPError("https://export.arxiv.org/api/query", 429, "Rate exceeded", {}, None)
        with mock.patch.object(_arxiv.urllib.request, "urlopen", side_effect=[error, TimeoutError()]):
            with self.assertRaises(TimeoutError):
                _arxiv.search(["keyword"], ["cs.CV"])

    def test_parser_rejects_non_atom_and_api_error_payloads(self):
        for body in (b"<html><body>Service unavailable</body></html>", feed('<entry><id>http://arxiv.org/api/errors#incorrect_id_format</id><title>Error</title></entry>')):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    _arxiv._parse_feed(body)


if __name__ == "__main__":
    unittest.main()
