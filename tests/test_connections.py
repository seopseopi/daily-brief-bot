import io
import json
import os
from pathlib import Path
import re
import unittest
from unittest import mock

from briefing import cli, pipeline, rendering
from sources import notices, study
from sources._shared import get_failures
import discord_sender


class ConnectionCheckTests(unittest.TestCase):
    def test_live_check_reports_only_health_and_never_sends_or_saves(self):
        private = "private-schedule-title"

        def collect(now):
            self.assertEqual(os.environ["BRIEF_READ_ONLY"], "1")
            self.assertEqual(os.environ["DISCORD_DRY_RUN"], "1")
            return {"schedule": {"secret": private},
                    "_source_health": {"schedule": {"status": "fresh", "duration_ms": 5, "failures": []}}}

        with (mock.patch.object(pipeline, "collect_data", side_effect=collect),
              mock.patch.object(rendering, "render_sections", return_value=[]),
              mock.patch.object(discord_sender, "send") as send,
              mock.patch.object(notices, "commit_pending") as commit,
              mock.patch("sys.stdout", new_callable=io.StringIO) as stdout):
            code = cli.run(["--check-connections", "--sections", "schedule", "--format", "json"])
        result = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertNotIn(private, stdout.getvalue())
        send.assert_not_called()
        commit.assert_not_called()

    def test_partial_and_unconfigured_sources_return_failure(self):
        for status in ("partial", "unconfigured", "unavailable"):
            with (self.subTest(status=status),
                  mock.patch.object(pipeline, "collect_data", return_value={"_source_health": {"schedule": {"status": status, "duration_ms": 0}}}),
                  mock.patch.object(rendering, "render_sections", return_value=[]),
                  mock.patch("sys.stdout", new_callable=io.StringIO) as stdout):
                code = cli.run(["--check-connections", "--format", "json"])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(stdout.getvalue())["ok"])

    def test_successful_empty_paper_search_is_not_a_connection_failure(self):
        get_failures()
        with mock.patch.object(study._arxiv, "search", return_value=[]):
            result = study.get_study()
        self.assertEqual(result["status"], "empty")
        self.assertNotIn("조회 실패", result["paper_title"])
        self.assertEqual(get_failures(), [])

        with (mock.patch.object(pipeline, "collect_data", return_value={"_source_health": {"study": {"status": "empty", "duration_ms": 5}}}),
              mock.patch.object(rendering, "render_sections", return_value=[]),
              mock.patch("sys.stdout", new_callable=io.StringIO)):
            self.assertEqual(cli.run(["--check-connections", "--format", "json"]), 0)

    def test_render_failure_is_a_failed_connection_check(self):
        data = {"_source_health": {"news": {"status": "ok", "duration_ms": 2}}, "_render_failed": ["news"]}
        with (mock.patch.object(pipeline, "collect_data", return_value=data),
              mock.patch.object(rendering, "render_sections", return_value=[]),
              mock.patch("sys.stdout", new_callable=io.StringIO) as stdout):
            self.assertEqual(cli.run(["--check-connections", "--format", "json"]), 1)
        self.assertEqual(json.loads(stdout.getvalue())["sources"][0]["status"], "unavailable")

    def test_connections_workflow_uses_same_operating_configuration_without_delivery(self):
        root = Path(__file__).parents[1]
        workflow = (root / ".github/workflows/connections.yml").read_text()
        delivery = (root / ".github/workflows/morning.yml").read_text()
        pattern = r"^          ([A-Z_]+): \$\{\{ (.*?) \}\}$"
        self.assertEqual(dict(re.findall(pattern, workflow, re.MULTILINE)),
                         dict(re.findall(pattern, delivery, re.MULTILINE)))
        self.assertIn("python main.py --check-connections --format json", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("schedule:", workflow)
