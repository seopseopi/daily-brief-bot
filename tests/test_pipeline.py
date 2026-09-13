import io
import unittest
from unittest import mock

import settings
from briefing.demo import DEMO_NOW
from briefing import pipeline
from briefing.rendering import render_sections
from sources._shared import fail, get_failures


class CollectionTests(unittest.TestCase):
    def tearDown(self):
        get_failures()

    def test_degraded_fallback_is_not_reported_as_healthy(self):
        def fallback(now):
            fail("과제채널")
            return []

        with (mock.patch.object(settings, "ENABLED_SECTIONS", {"schedule"}),
              mock.patch.object(pipeline, "LOADERS", {"assignments": fallback, "schedule": lambda now: {"status": "fresh"}}),
              mock.patch("sys.stdout", new_callable=io.StringIO)):
            data = pipeline.collect_data(DEMO_NOW)
        self.assertEqual(data["_source_health"]["assignments"]["status"], "partial")
        self.assertEqual(data["_source_health"]["assignments"]["failures"], ["과제채널"])
        self.assertEqual(data["_source_health"]["schedule"]["status"], "fresh")
        with mock.patch.object(settings, "ENABLED_SECTIONS", {"schedule"}):
            body = render_sections(DEMO_NOW, data)[0]["description"]
        self.assertIn("과제 조회 실패", body)
        self.assertNotIn("등록된 미완료 과제 없음", body)

    def test_failed_source_does_not_abort_other_sources_or_log_private_errors(self):
        secret = "private-url-token"

        def broken(now):
            raise ValueError(secret)

        with (mock.patch.object(settings, "ENABLED_SECTIONS", {"weather", "news"}),
              mock.patch.object(pipeline, "LOADERS", {"weather": broken, "news": lambda now: []}),
              mock.patch("sys.stdout", new_callable=io.StringIO) as stdout):
            data = pipeline.collect_data(DEMO_NOW)
        self.assertEqual(data["news"], [])
        self.assertNotIn("weather", data)
        self.assertEqual(data["_source_health"]["weather"]["status"], "unavailable")
        self.assertNotIn(secret, stdout.getvalue())
