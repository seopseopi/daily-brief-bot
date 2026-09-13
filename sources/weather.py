"""Action-oriented weather forecast from Open-Meteo.

Open-Meteo exposes model forecasts, not a guaranteed on-site observation. The
UI therefore labels every value as a forecast and includes its model time.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math
import urllib.parse

import settings
from sources import _market
from sources._shared import KST, fail

API_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
ATTRIBUTION_URL = "https://open-meteo.com/en/docs"
RAIN_WINDOW_THRESHOLD = 50
HOURLY_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "precipitation_probability",
    "wind_speed_10m",
)

WEATHER_CODES = {
    0: "맑음",
    1: "대체로 맑음",
    2: "구름 조금",
    3: "흐림",
    45: "안개",
    48: "서리 안개",
    51: "약한 이슬비",
    53: "이슬비",
    55: "강한 이슬비",
    56: "어는 이슬비",
    57: "강한 어는 이슬비",
    61: "약한 비",
    63: "비",
    65: "강한 비",
    66: "어는 비",
    67: "강한 어는 비",
    71: "약한 눈",
    73: "눈",
    75: "강한 눈",
    77: "싸락눈",
    80: "약한 소나기",
    81: "소나기",
    82: "강한 소나기",
    85: "약한 눈 소나기",
    86: "강한 눈 소나기",
    95: "뇌우",
    96: "우박 동반 뇌우",
    99: "강한 우박 동반 뇌우",
}


def _advice(
    low: float,
    high: float,
    rain: int,
    wind: float,
    *,
    apparent: float | None = None,
) -> list[str]:
    advice = []
    if rain >= 60:
        advice.append("우산을 꼭 챙기세요")
    elif rain >= 35:
        advice.append("접이식 우산을 챙기면 안전해요")
    if apparent is not None and apparent >= 33:
        advice.append(f"체감온도 {apparent:.0f}°C 예보 · 통풍이 잘 되는 옷과 물을 챙기세요")
    elif high >= 33:
        advice.append("한낮 야외활동은 줄이고 물을 챙기세요")
    elif low <= 5:
        advice.append("낮은 기온에 대비해 따뜻한 겉옷을 챙기세요")
    elif high - low >= 10:
        advice.append("일교차가 커서 얇은 겉옷이 유용해요")
    if wind >= 35:
        advice.append(f"바람 {wind:.0f}km/h 예보 · 야외 이동 시 강한 바람에 주의하세요")
    return advice or ["외출 전 시간별 예보를 확인하세요"]


def _model_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=KST) if parsed.tzinfo is None else parsed.astimezone(KST)


def _hourly_number(hourly: dict, field: str, index: int) -> float | None:
    """A missing or malformed optional cell must not discard other forecasts."""
    values = hourly.get(field)
    if not isinstance(values, list) or index >= len(values):
        return None
    value = values[index]
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if field == "precipitation_probability" and not 0 <= number <= 100:
        return None
    if field == "wind_speed_10m" and number < 0:
        return None
    return number


def _next_rain(rows: list[dict], now: datetime) -> dict | None:
    """Return the first likely precipitation window, respecting hourly gaps.

    Open-Meteo probabilities describe the *preceding* hour, so 09:00 is the
    probability for 08:00–09:00. Only a contiguous lower-probability interval
    confirms the end; a missing value or the end of the feed does not.
    """
    window = None
    previous_end = None
    for row in rows:
        interval_end = row["time"]
        if interval_end <= now:
            continue
        interval_start = interval_end - timedelta(hours=1)
        probability = row["precipitation_probability"]
        if window is not None and (
            interval_start != previous_end or probability is None
        ):
            break
        if probability is not None and probability >= RAIN_WINDOW_THRESHOLD:
            if window is None:
                window = {
                    "start": interval_start,
                    "end": None,
                    "probability": round(probability),
                    "ongoing": interval_start <= now,
                }
            else:
                window["probability"] = max(window["probability"], round(probability))
            previous_end = interval_end
        elif window is not None:
            window["end"] = interval_start
            break
    return window


def _hourly_outlook(hourly: object, now: datetime) -> tuple[dict, list[dict]]:
    outlook = {"periods": [], "next_rain": None, "hourly_status": "unavailable"}
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        return outlook, []

    rows_by_time = {}
    malformed = False
    for index, value in enumerate(hourly["time"][:48]):
        try:
            forecast_time = _model_time(value)
        except (TypeError, ValueError, OverflowError):
            malformed = True
            continue
        if forecast_time.date() != now.date() or forecast_time < now:
            continue
        if forecast_time.minute or forecast_time.second or forecast_time.microsecond:
            malformed = True
            continue
        if forecast_time in rows_by_time:
            malformed = True
            continue
        rows_by_time[forecast_time] = {
            "time": forecast_time,
            **{field: _hourly_number(hourly, field, index) for field in HOURLY_FIELDS},
        }
    rows = sorted(rows_by_time.values(), key=lambda row: row["time"])
    if not any(any(row[field] is not None for field in HOURLY_FIELDS) for row in rows):
        return outlook, []

    next_hour = now.replace(minute=0, second=0, microsecond=0)
    if next_hour < now:
        next_hour += timedelta(hours=1)
    expected_hours = 24 - next_hour.hour if next_hour.date() == now.date() else 0
    complete = len(rows) == expected_hours and not malformed and all(
        row[field] is not None for row in rows for field in HOURLY_FIELDS
    )
    outlook["hourly_status"] = "available" if complete else "partial"
    for label, start_hour, end_hour in (("오전", 0, 12), ("오후", 12, 18), ("저녁", 18, 24)):
        samples = [
            row for row in rows
            if start_hour <= row["time"].hour < end_hour
            and row["temperature_2m"] is not None
        ]
        if not samples:
            continue
        start, end = samples[0]["time"], samples[-1]["time"]
        # Temperature samples are instantaneous; precipitation values describe
        # preceding hours and must fall inside the displayed sample range.
        rain_values = [
            row["precipitation_probability"] for row in rows
            if start < row["time"] <= end and row["precipitation_probability"] is not None
        ]
        wind_values = [row["wind_speed_10m"] for row in samples if row["wind_speed_10m"] is not None]
        temperatures = [row["temperature_2m"] for row in samples]
        outlook["periods"].append({
            "label": label,
            "start": start,
            "end": end,
            "temperature_min": min(temperatures),
            "temperature_max": max(temperatures),
            "rain_probability": round(max(rain_values)) if rain_values else None,
            "wind_speed": max(wind_values) if wind_values else None,
        })
    outlook["next_rain"] = _next_rain(rows, now)
    return outlook, rows


def _air_quality(now: datetime) -> dict | None:
    params = {
        "latitude": settings.LOCATION_LATITUDE,
        "longitude": settings.LOCATION_LONGITUDE,
        "timezone": "Asia/Seoul",
        "current": "pm10,pm2_5,us_aqi",
    }
    try:
        data = _market.fetch_json(AIR_QUALITY_API_URL + "?" + urllib.parse.urlencode(params))
        current = data["current"]
        model_time = _model_time(current["time"])
        if abs((now - model_time).total_seconds()) > 3 * 3600:
            raise ValueError("air-quality model value is stale")
        aqi = int(current["us_aqi"])
        if aqi <= 50:
            label = "좋음"
        elif aqi <= 100:
            label = "보통"
        elif aqi <= 150:
            label = "민감군 주의"
        else:
            label = "나쁨"
        return {
            "aqi": aqi,
            "label": label,
            "pm10": float(current["pm10"]),
            "pm2_5": float(current["pm2_5"]),
            "as_of": model_time,
        }
    except Exception as exc:
        print(f"[경고] 대기질 조회 실패: {type(exc).__name__}")
        fail("대기질")
        return None


def get_weather(now: datetime | None = None) -> dict:
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    else:
        now = now.astimezone(KST)
    params = {
        "latitude": settings.LOCATION_LATITUDE,
        "longitude": settings.LOCATION_LONGITUDE,
        "timezone": "Asia/Seoul",
        "forecast_days": 1,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "hourly": ",".join(HOURLY_FIELDS),
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    try:
        data = _market.fetch_json(url)
        current = data["current"]
        daily = data["daily"]
        if daily["time"][0] != now.date().isoformat():
            raise ValueError("weather response is not for today")
        model_time = _model_time(current["time"])
        if abs((now - model_time).total_seconds()) > 3 * 3600:
            raise ValueError("weather model value is stale")
        low = float(daily["temperature_2m_min"][0])
        high = float(daily["temperature_2m_max"][0])
        rain = int(daily["precipitation_probability_max"][0] or 0)
        wind = float(current["wind_speed_10m"] or 0)
        apparent = float(current["apparent_temperature"])
        outlook, hourly_rows = _hourly_outlook(data.get("hourly"), now)
        remaining_wind = max([wind] + [
            row["wind_speed_10m"] for row in hourly_rows if row["wind_speed_10m"] is not None
        ])
        remaining_apparent = max([apparent] + [
            row["apparent_temperature"] for row in hourly_rows if row["apparent_temperature"] is not None
        ])
        result = {
            "status": "fresh",
            "location": settings.LOCATION_NAME,
            "condition": WEATHER_CODES.get(int(current["weather_code"]), f"기상코드 {current['weather_code']}"),
            "temperature": float(current["temperature_2m"]),
            "apparent_temperature": apparent,
            "low": low,
            "high": high,
            "rain_probability": rain,
            "wind_speed": wind,
            "advice": _advice(low, high, rain, remaining_wind, apparent=remaining_apparent),
            "as_of": model_time,
            "source": "Open-Meteo 예보",
            "source_url": ATTRIBUTION_URL,
            **outlook,
        }
        result["air_quality"] = _air_quality(now)
        if result["air_quality"] and result["air_quality"]["aqi"] > 100:
            result["advice"].append("대기질이 좋지 않아 민감군은 마스크를 고려하세요")
        return result
    except Exception as exc:
        print(f"[경고] 날씨 조회 실패: {type(exc).__name__}")
        fail("날씨")
        return {
            "status": "unavailable",
            "location": settings.LOCATION_NAME,
            "source": "Open-Meteo 예보",
            "source_url": ATTRIBUTION_URL,
        }
