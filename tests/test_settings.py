import os
import unittest
from unittest import mock

import settings


class SettingsParsingTests(unittest.TestCase):
    def test_calendar_urls_accept_json_without_splitting_url_commas(self):
        raw = '["https://calendar.example/a,b.ics", "https://calendar.example/c.ics"]'
        with mock.patch.dict(os.environ, {"CALENDAR_ICS_URLS": raw}, clear=True):
            result = settings.env_list("CALENDAR_ICS_URLS")

        self.assertEqual(
            result,
            ["https://calendar.example/a,b.ics", "https://calendar.example/c.ics"],
        )

    def test_list_accepts_newlines_and_semicolons(self):
        raw = "weather;schedule\nnews"
        with mock.patch.dict(os.environ, {"BRIEF_SECTIONS": raw}, clear=True):
            result = settings.env_list("BRIEF_SECTIONS")

        self.assertEqual(result, ["weather", "schedule", "news"])

    def test_invalid_numbers_use_explicit_defaults(self):
        with mock.patch.dict(
            os.environ,
            {"BRIEF_LATITUDE": "invalid", "NEWS_MAX_AGE_HOURS": "invalid"},
            clear=True,
        ):
            self.assertEqual(settings.env_float("BRIEF_LATITUDE", 37.5665), 37.5665)
            self.assertEqual(settings.env_int("NEWS_MAX_AGE_HOURS", 36), 36)

    def test_boolean_parser_requires_an_explicit_truthy_value(self):
        with mock.patch.dict(
            os.environ,
            {"YES_VALUE": "yes", "NO_VALUE": "false"},
            clear=True,
        ):
            self.assertTrue(settings.env_bool("YES_VALUE"))
            self.assertFalse(settings.env_bool("NO_VALUE", default=True))
            self.assertTrue(settings.env_bool("MISSING", default=True))

    def test_market_holdings_default_to_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(settings.env_symbols("MARKET_HOLDINGS_KR", "KR"), [])
            self.assertEqual(settings.env_symbols("MARKET_HOLDINGS_US", "US"), [])

    def test_market_holdings_accept_json_and_validate_by_market(self):
        with mock.patch.dict(
            os.environ,
            {
                "KR": '["005930", "bad", "005930", "000660"]',
                "US": '["aapl", "BRK-B", "bad ticker", "AAPL"]',
            },
            clear=True,
        ):
            self.assertEqual(settings.env_symbols("KR", "KR"), ["005930", "000660"])
            self.assertEqual(settings.env_symbols("US", "US"), ["AAPL", "BRK-B"])

    def test_market_holdings_accept_newlines_and_semicolons(self):
        with mock.patch.dict(os.environ, {"HOLDINGS": "AAPL;msft\nBRK-B"}, clear=True):
            result = settings.env_symbols("HOLDINGS", "US")

        self.assertEqual(result, ["AAPL", "MSFT", "BRK-B"])

    def test_malformed_holdings_json_fails_closed(self):
        with mock.patch.dict(os.environ, {"HOLDINGS": '["AAPL"'}, clear=True):
            self.assertEqual(settings.env_symbols("HOLDINGS", "US"), [])


if __name__ == "__main__":
    unittest.main()
