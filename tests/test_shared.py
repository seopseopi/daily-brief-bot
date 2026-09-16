import unittest
from unittest import mock

from sources import _shared


class TranslationFallbackTests(unittest.TestCase):
    def test_translation_failure_keeps_excerpt_short(self):
        original = "A long community post. " * 100
        with mock.patch.object(_shared._translate, "translate_en_ko", side_effect=OSError):
            result = _shared.tr(original, cap=160)
        self.assertLessEqual(len(result), 160)
        self.assertTrue(result.endswith("…"))
        self.assertTrue(original.startswith(result[:-1]))
