"""Concurrent source collection with isolated failures and safe diagnostics."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from time import monotonic
import settings
from sources import assignments, community, market, news, notices, schedule, sports, study, weather
from sources._shared import fail, capture_failures

LOADERS = {
    "weather": weather.get_weather,
    "schedule": schedule.get_schedule,
    "assignments": assignments.get_assignments,
    "notices": notices.get_notices,
    "news": news.get_news,
    "market": market.get_market,
    "sports": sports.get_sports,
    "study": study.get_study,
    "community": community.get_community,
}


def _load(name, loader, now):
    started = monotonic()
    with capture_failures() as failures:
        try:
            if name in {"community", "weather", "schedule", "news", "assignments"}:
                value = loader(now=now)
            else:
                value = loader()
            status = value.get("status", "ok") if isinstance(value, dict) else "ok"
            if failures and status not in {"unavailable", "unconfigured"}:
                status = "partial"
            return value, {"status": status, "duration_ms": round((monotonic() - started) * 1000), "failures": failures}
        except Exception as exc:
            print(f"[경고] {name} 전체 처리 실패: {type(exc).__name__}")
            fail(name)
            return None, {"status": "unavailable", "duration_ms": round((monotonic() - started) * 1000),
                          "error_type": type(exc).__name__, "failures": failures}


def collect_data(now: datetime) -> dict:
    wanted = set(settings.ENABLED_SECTIONS)
    if "schedule" in wanted:
        wanted.add("assignments")
    selected = {name: loader for name, loader in LOADERS.items() if name in wanted}
    results = {"_source_health": {}}
    with ThreadPoolExecutor(max_workers=min(8, len(selected) or 1), thread_name_prefix="brief") as pool:
        futures = {}
        for name, loader in selected.items():
            future = pool.submit(_load, name, loader, now)
            futures[future] = name
        for future in as_completed(futures):
            name = futures[future]
            value, health = future.result()
            results["_source_health"][name] = health
            if value is not None:
                results[name] = value
    for name in selected:
        health = results["_source_health"][name]
        print(f"[수집] {name}: {health['status']} · {health['duration_ms']}ms")
    return results
