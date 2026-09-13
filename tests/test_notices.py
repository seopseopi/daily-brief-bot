import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import main
from briefing.demo import DEMO_NOW
from sources import notices


class NoticeAcknowledgementTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "seen.json"
        self.path.write_text(json.dumps({"test": ["old"]}))
        self.patches = [mock.patch.object(notices, "SEEN_NOTICES_PATH", str(self.path)),
                        mock.patch.object(notices, "NOTICE_SITES", [("test", "공개 공지", lambda: [("new", "새 공지", "https://example.com/notice")])]),
                        mock.patch.dict(os.environ, {}, clear=True)]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        notices.discard_pending()
        for patch in reversed(self.patches):
            patch.stop()
        self.directory.cleanup()

    def test_collecting_does_not_acknowledge_until_delivery_succeeds(self):
        result = notices.get_notices()
        self.assertEqual(result[0][1][0][0], "새 공지")
        self.assertEqual(json.loads(self.path.read_text()), {"test": ["old"]})
        notices.commit_pending()
        self.assertEqual(json.loads(self.path.read_text()), {"test": ["new"]})

    def test_failed_delivery_keeps_new_notice_for_next_run(self):
        def build(now):
            notices.get_notices()
            return []
        with (mock.patch.object(main, "build_brief", side_effect=build),
              mock.patch.object(main.ds, "send", side_effect=RuntimeError("failed"))):
            with self.assertRaises(RuntimeError):
                main.main()
        self.assertEqual(json.loads(self.path.read_text()), {"test": ["old"]})
        self.assertTrue(notices.get_notices())

    def test_dry_run_does_not_acknowledge(self):
        notices.get_notices()
        with mock.patch.dict(os.environ, {"DISCORD_DRY_RUN": "1"}):
            notices.commit_pending()
        self.assertEqual(json.loads(self.path.read_text()), {"test": ["old"]})

    def test_failed_notice_render_does_not_acknowledge_unshown_notice(self):
        def collect(now):
            notices.get_notices()
            return {"notices": [("invalid shape",)]}
        with (mock.patch.object(main.settings, "ENABLED_SECTIONS", {"notices"}),
              mock.patch.object(main, "collect_data", side_effect=collect)):
            main.build_brief(DEMO_NOW)
            notices.commit_pending()
        self.assertEqual(json.loads(self.path.read_text()), {"test": ["old"]})
