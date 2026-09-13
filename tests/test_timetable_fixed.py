import io
import json
import unittest
from unittest import mock

from sources import timetable_fixed


class FixedTimetableParsingTests(unittest.TestCase):
    def test_empty_configuration_has_no_public_default_schedule(self):
        self.assertEqual(timetable_fixed.parse_fixed_timetable(""), {})

    def test_valid_json_is_normalized_and_sorted(self):
        raw = json.dumps(
            {
                "0": [
                    ["13:00", "14:00", "오후 일정"],
                    ["09:00", "10:30", "오전 일정", "선택 메모"],
                ],
                "6": [],
            },
            ensure_ascii=False,
        )

        result = timetable_fixed.parse_fixed_timetable(raw)

        self.assertEqual(
            result[0],
            [
                ("09:00", "10:30", "오전 일정", "선택 메모"),
                ("13:00", "14:00", "오후 일정", ""),
            ],
        )
        self.assertEqual(result[6], [])

    def test_invalid_or_overlapping_schedule_raises_without_user_content(self):
        invalid_values = [
            "not-json",
            "[]",
            '{"7": []}',
            '{"0": [["9:00", "10:00", "bad time"]]}',
            '{"0": [["10:00", "09:00", "backwards"]]}',
            '{"0": [["09:00", "11:00", "one"], ["10:30", "12:00", "two"]]}',
            '{"0": [["09:00", "10:00", ""]]}',
        ]

        for raw in invalid_values:
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "FIXED_TIMETABLE_JSON"):
                    timetable_fixed.parse_fixed_timetable(raw)

    def test_invalid_private_value_is_not_logged(self):
        private_marker = "PRIVATE-SCHEDULE-MARKER"
        raw = json.dumps({"0": [["invalid", "10:00", private_marker]]})
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            with self.assertRaises(ValueError) as raised:
                timetable_fixed.parse_fixed_timetable(raw)

        self.assertNotIn(private_marker, str(raised.exception))
        self.assertNotIn(private_marker, stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
