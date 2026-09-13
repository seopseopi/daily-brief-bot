import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import main
import settings
from briefing import cli
from briefing.demo import demo_data, DEMO_NOW
from briefing.export import export_brief
from briefing.rendering import render_sections


class PreviewTests(unittest.TestCase):
    def test_demo_does_not_call_network_send_or_collect(self):
        with (mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")),
              mock.patch.object(main, "collect_data", side_effect=AssertionError("collect")),
              mock.patch.object(main.ds, "send", side_effect=AssertionError("send")),
              mock.patch("sys.stdout", new_callable=io.StringIO) as stdout):
            self.assertEqual(cli.run(["--demo", "--format", "json"]), 0)
        output = json.loads(stdout.getvalue())
        self.assertEqual(len(output["embeds"]), 9)
        self.assertIn("가상 예시", output["embeds"][0]["description"])

    def test_real_preview_is_read_only_and_diagnostics_go_to_stderr(self):
        def collect(now):
            self.assertEqual(os.environ["BRIEF_READ_ONLY"], "1")
            self.assertEqual(os.environ["DISCORD_DRY_RUN"], "1")
            print("diagnostic")
            return demo_data(now)

        before = {name: os.environ.get(name) for name in ("BRIEF_READ_ONLY", "DISCORD_DRY_RUN")}
        with (mock.patch.object(main, "collect_data", side_effect=collect),
              mock.patch.object(main.ds, "send", side_effect=AssertionError("send")),
              mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
              mock.patch("sys.stderr", new_callable=io.StringIO) as stderr):
            cli.run(["--preview", "--sections", "weather", "--format", "json"])
        self.assertEqual(len(json.loads(stdout.getvalue())["embeds"]), 2)
        self.assertIn("diagnostic", stderr.getvalue())
        self.assertEqual(before, {name: os.environ.get(name) for name in before})

    def test_unknown_section_fails_before_any_collection(self):
        with (mock.patch.object(main, "collect_data") as collect,
              mock.patch("sys.stderr", new_callable=io.StringIO)):
            with self.assertRaises(SystemExit) as caught:
                cli.run(["--preview", "--sections", "wether"])
        self.assertEqual(caught.exception.code, 2)
        collect.assert_not_called()

    def test_output_requires_preview_instead_of_accidentally_sending(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                cli.run(["--format", "html"])

    def test_real_preview_file_is_private_even_when_replacing_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "brief.md"
            output.write_text("old")
            output.chmod(0o644)
            with (mock.patch.object(main, "build_brief", return_value=[{"title": "개인 일정", "description": "내용"}]),
                  mock.patch("sys.stderr", new_callable=io.StringIO)):
                cli.run(["--preview", "--format", "markdown", "--output", str(output)])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertIn("개인 일정", output.read_text())

    def test_compact_keeps_every_deadline_and_original_link(self):
        data = demo_data()
        with mock.patch.object(settings, "ENABLED_SECTIONS", {"schedule", "news", "study", "community"}):
            full = export_brief(render_sections(DEMO_NOW, data, compact=False), "markdown")
            compact = export_brief(render_sections(DEMO_NOW, data, compact=True), "markdown")
        self.assertLess(len(compact), len(full))
        for _, name, _ in data["assignments"]:
            self.assertIn(name, compact)
        self.assertIn(data["news"][0]["url"], compact)
        self.assertIn(data["community"][0]["url"], compact)

    def test_html_escapes_source_content_and_unsafe_links(self):
        output = export_brief([{"title": '<script>alert(1)</script>',
                                "description": '<img src=x onerror=alert(1)>\n[click](javascript:alert(1))\n[원문](https://example.com/?a=1&b=2)'}], "html")
        self.assertNotIn("<script>", output)
        self.assertNotIn("<img ", output)
        self.assertNotIn('href="javascript:', output)
        self.assertIn('href="https://example.com/?a=1&amp;b=2"', output)


class DoctorTests(unittest.TestCase):
    def test_doctor_never_echoes_secrets_or_calls_network(self):
        secret = "test-secret-not-for-output"
        with (mock.patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": secret, "DISCORD_BOT_TOKEN": secret,
                                          "ASSIGNMENT_CHANNEL_ID": secret, "ANTHROPIC_API_KEY": secret}),
              mock.patch.object(settings, "CALENDAR_ICS_URLS", [f"https://example.com/{secret}"]),
              mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")),
              mock.patch("sys.stdout", new_callable=io.StringIO) as stdout):
            self.assertEqual(cli.run(["--doctor", "--format", "json"]), 0)
        self.assertNotIn(secret, stdout.getvalue())
        self.assertTrue(json.loads(stdout.getvalue())["ok"])

    def test_invalid_coordinates_fail_with_sanitized_message(self):
        with mock.patch.object(settings, "ENABLED_SECTIONS", {"weather"}):
            for invalid in ("NaN", "inf", "91", "wrong-value"):
                with self.subTest(invalid=invalid), mock.patch.dict(os.environ, {"BRIEF_LATITUDE": invalid}):
                    errors = cli.configuration_errors()
                    self.assertTrue(errors)
                    self.assertNotIn(invalid, " ".join(errors))
