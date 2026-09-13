import unittest
import urllib.parse
from datetime import datetime, timezone
from unittest import mock

import settings
from sources import weather
from sources._shared import KST, get_failures


NOW = datetime(2026, 9, 11, 7, 30, tzinfo=KST)


def weather_fixture(*, model_time="2026-09-11T07:00", forecast_date="2026-09-11"):
    return {
        "latitude": 37.57,
        "longitude": 126.98,
        "timezone": "Asia/Seoul",
        "current": {
            "time": model_time,
            "temperature_2m": 21.5,
            "apparent_temperature": 20.2,
            "weather_code": 61,
            "wind_speed_10m": 12.3,
        },
        "daily": {
            "time": [forecast_date],
            "temperature_2m_max": [27.0],
            "temperature_2m_min": [16.0],
            "precipitation_probability_max": [70],
        },
    }


def air_quality_fixture(*, model_time="2026-09-11T07:00", aqi=80):
    return {
        "current": {
            "time": model_time,
            "pm10": 32.0,
            "pm2_5": 14.5,
            "us_aqi": aqi,
        }
    }


def hourly_fixture():
    return {
        "time": [f"2026-09-11T{hour:02d}:00" for hour in range(24)],
        "temperature_2m": [20 + hour / 2 for hour in range(24)],
        "apparent_temperature": [20 + hour / 2 for hour in range(24)],
        "precipitation_probability": [10] * 24,
        "wind_speed_10m": [12.0] * 24,
    }


class WeatherFixtureTests(unittest.TestCase):
    def setUp(self):
        get_failures()

    def tearDown(self):
        get_failures()

    def test_fresh_forecast_preserves_model_time_and_actionable_values(self):
        fixture = weather_fixture()
        with (
            mock.patch.object(settings, "LOCATION_NAME", "서울 종로구"),
            mock.patch.object(settings, "LOCATION_LATITUDE", 37.57),
            mock.patch.object(settings, "LOCATION_LONGITUDE", 126.98),
            mock.patch.object(
                weather._market,
                "fetch_json",
                side_effect=[fixture, air_quality_fixture()],
            ) as fetch,
        ):
            result = weather.get_weather(NOW)

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["location"], "서울 종로구")
        self.assertEqual(result["condition"], "약한 비")
        self.assertEqual(result["as_of"], NOW.replace(hour=7, minute=0))
        self.assertEqual(result["rain_probability"], 70)
        self.assertEqual(result["air_quality"]["label"], "보통")
        self.assertEqual(result["air_quality"]["as_of"], NOW.replace(hour=7, minute=0))
        self.assertIn("우산을 꼭 챙기세요", result["advice"])
        self.assertIn("일교차", " ".join(result["advice"]))

        query = urllib.parse.parse_qs(urllib.parse.urlparse(fetch.call_args_list[0].args[0]).query)
        self.assertEqual(query["timezone"], ["Asia/Seoul"])
        self.assertEqual(query["forecast_days"], ["1"])
        self.assertEqual(query["latitude"], ["37.57"])
        self.assertIn("precipitation_probability", query["hourly"][0])
        self.assertEqual(query["temperature_unit"], ["celsius"])
        self.assertEqual(query["wind_speed_unit"], ["kmh"])

    def test_model_value_older_than_three_hours_is_rejected(self):
        with mock.patch.object(
            weather._market,
            "fetch_json",
            return_value=weather_fixture(model_time="2026-09-11T04:00"),
        ):
            result = weather.get_weather(NOW)

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("날씨", get_failures())

    def test_forecast_for_another_date_is_rejected(self):
        with mock.patch.object(
            weather._market,
            "fetch_json",
            return_value=weather_fixture(forecast_date="2026-09-10"),
        ):
            result = weather.get_weather(NOW)

        self.assertEqual(result["status"], "unavailable")

    def test_three_hour_freshness_boundary_is_accepted(self):
        with mock.patch.object(weather._market, "fetch_json", side_effect=[
            weather_fixture(model_time="2026-09-11T04:30"),
            air_quality_fixture(model_time="2026-09-11T04:30"),
        ]):
            result = weather.get_weather(NOW)

        self.assertEqual(result["status"], "fresh")

    def test_utc_now_is_converted_before_forecast_date_validation(self):
        utc_now = datetime(2026, 9, 10, 22, 30, tzinfo=timezone.utc)
        with mock.patch.object(
            weather._market,
            "fetch_json",
            side_effect=[weather_fixture(), air_quality_fixture()],
        ):
            result = weather.get_weather(utc_now)

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["as_of"].date(), NOW.date())

    def test_stale_air_quality_does_not_invalidate_fresh_weather(self):
        with mock.patch.object(weather._market, "fetch_json", side_effect=[
            weather_fixture(),
            air_quality_fixture(model_time="2026-09-11T03:00"),
        ]):
            result = weather.get_weather(NOW)

        self.assertEqual(result["status"], "fresh")
        self.assertIsNone(result["air_quality"])
        self.assertIn("대기질", get_failures())


class HourlyWeatherTests(unittest.TestCase):
    def setUp(self):
        get_failures()

    def tearDown(self):
        get_failures()

    def forecast(self, hourly, now=NOW):
        fixture = weather_fixture(model_time=now.isoformat())
        fixture["hourly"] = hourly
        with mock.patch.object(weather._market, "fetch_json", side_effect=[
            fixture, air_quality_fixture(model_time=now.isoformat()),
        ]):
            return weather.get_weather(now)

    def test_periods_exclude_elapsed_hours_and_bound_reading_to_three_windows(self):
        hourly = hourly_fixture()
        hourly["temperature_2m"][6] = -10
        hourly["precipitation_probability"][6] = 100
        result = self.forecast(hourly)

        self.assertEqual(result["hourly_status"], "available")
        self.assertEqual([period["label"] for period in result["periods"]], ["오전", "오후", "저녁"])
        morning = result["periods"][0]
        self.assertEqual(morning["start"], NOW.replace(hour=8, minute=0))
        self.assertEqual(morning["end"], NOW.replace(hour=11, minute=0))
        self.assertEqual(morning["temperature_min"], 24)
        self.assertEqual(morning["temperature_max"], 25.5)
        self.assertEqual(morning["rain_probability"], 10)
        self.assertIsNone(result["next_rain"])

    def test_evening_run_only_returns_remaining_evening_forecast(self):
        now = NOW.replace(hour=19)
        result = self.forecast(hourly_fixture(), now)

        self.assertEqual(result["hourly_status"], "available")
        self.assertEqual(len(result["periods"]), 1)
        self.assertEqual(result["periods"][0]["label"], "저녁")
        self.assertEqual(result["periods"][0]["start"], now.replace(hour=20, minute=0))

    def test_rain_window_uses_preceding_hour_and_first_contiguous_dry_interval(self):
        hourly = hourly_fixture()
        hourly["precipitation_probability"][9:11] = [50, 80]
        hourly["precipitation_probability"][15] = 90
        result = self.forecast(hourly)

        self.assertEqual(result["next_rain"], {
            "start": NOW.replace(hour=8, minute=0),
            "end": NOW.replace(hour=10, minute=0),
            "probability": 80,
            "ongoing": False,
        })

    def test_rain_probability_for_current_interval_is_flagged_as_ongoing(self):
        hourly = hourly_fixture()
        hourly["precipitation_probability"][8] = 70
        result = self.forecast(hourly)

        self.assertTrue(result["next_rain"]["ongoing"])
        self.assertEqual(result["next_rain"]["start"], NOW.replace(hour=7, minute=0))
        self.assertEqual(result["next_rain"]["end"], NOW.replace(hour=8, minute=0))

    def test_unknown_probability_or_missing_hour_cannot_confirm_rain_end(self):
        for missing in ("null", "gap", "end_of_feed"):
            with self.subTest(missing=missing):
                hourly = hourly_fixture()
                hourly["precipitation_probability"][9] = 70
                if missing == "null":
                    hourly["precipitation_probability"][10] = None
                elif missing == "gap":
                    for values in hourly.values():
                        del values[10]
                else:
                    for values in hourly.values():
                        del values[10:]
                result = self.forecast(hourly)

                self.assertEqual(result["status"], "fresh")
                self.assertEqual(result["hourly_status"], "partial")
                self.assertIsNone(result["next_rain"]["end"])

    def test_null_temperatures_do_not_discard_valid_rain_forecast(self):
        hourly = hourly_fixture()
        hourly["temperature_2m"] = [None] * 24
        hourly["precipitation_probability"][10] = 70
        result = self.forecast(hourly)

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["hourly_status"], "partial")
        self.assertEqual(result["periods"], [])
        self.assertEqual(result["next_rain"]["start"], NOW.replace(hour=9, minute=0))
        self.assertNotIn("날씨", get_failures())

    def test_malformed_optional_data_preserves_current_weather_and_air_quality(self):
        for hourly in (None, [], {"time": "bad"}, {"time": [None, "bad"]}, {
            "time": ["2026-09-11T09:00"],
            "temperature_2m": [float("nan")],
            "apparent_temperature": [float("inf")],
            "precipitation_probability": [-1],
            "wind_speed_10m": [-3],
        }):
            with self.subTest(hourly=hourly):
                result = self.forecast(hourly)
                self.assertEqual(result["status"], "fresh")
                self.assertEqual(result["hourly_status"], "unavailable")
                self.assertEqual(result["periods"], [])
                self.assertIsNone(result["next_rain"])
                self.assertEqual(result["air_quality"]["label"], "보통")
                self.assertNotIn("날씨", get_failures())

    def test_partial_arrays_keep_useful_temperature_without_inventing_zero_rain(self):
        hourly = hourly_fixture()
        hourly["precipitation_probability"] = [10] * 8
        hourly["wind_speed_10m"][10] = "bad"
        hourly["time"][9] = "bad"
        result = self.forecast(hourly)

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["hourly_status"], "partial")
        self.assertEqual(len(result["periods"]), 3)
        self.assertIsNone(result["periods"][0]["rain_probability"])
        self.assertIsNone(result["next_rain"])

    def test_remaining_heat_and_wind_are_actionable_without_hiding_wind_warning(self):
        hourly = hourly_fixture()
        hourly["apparent_temperature"][14] = 36
        hourly["wind_speed_10m"][18] = 42
        result = self.forecast(hourly)

        advice = " ".join(result["advice"])
        self.assertIn("우산", advice)
        self.assertIn("체감온도 36°C", advice)
        self.assertIn("바람 42km/h", advice)

    def test_elapsed_heat_and_wind_do_not_trigger_remaining_day_advice(self):
        hourly = hourly_fixture()
        hourly["apparent_temperature"][5] = 36
        hourly["wind_speed_10m"][5] = 42
        result = self.forecast(hourly)

        advice = " ".join(result["advice"])
        self.assertNotIn("체감온도 36°C", advice)
        self.assertNotIn("바람 42km/h", advice)


if __name__ == "__main__":
    unittest.main()
