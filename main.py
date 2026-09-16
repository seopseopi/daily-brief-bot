"""Daily brief entry point; rendering and source collection live in briefing/."""

from datetime import datetime, timedelta
import json
import os
import time

import discord_sender as ds
import settings
from sources._shared import KST, get_failures
from sources import notices
from briefing.pipeline import collect_data, LOADERS
from briefing.rendering import (
    build_header, build_weather, build_schedule, build_notices, build_market,
    build_news, build_sports, build_study, build_community, render_sections,
    _deterministic_highlights,
)

DELIVERY_STATE_PATH = "data/delivery_state.json"


def _wait_until(target: datetime) -> None:
    """Recheck wall time in short intervals, including after a clock adjustment."""
    while True:
        remaining = (target - datetime.now(KST)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 30))


def _scheduled_target(now: datetime) -> datetime | None:
    if (os.environ.get("GITHUB_EVENT_NAME") != "schedule"
            or settings.env_bool("DISCORD_DRY_RUN") or settings.env_bool("BRIEF_READ_ONLY")):
        return None
    return now.astimezone(KST).replace(hour=8, minute=0, second=0, microsecond=0)


def build_brief(now: datetime | None = None) -> list[dict]:
    now = (now or datetime.now(KST)).astimezone(KST)
    get_failures()  # Every build owns its own failure report.
    data = collect_data(now)
    embeds = render_sections(now, data)
    if "notices" in data.get("_render_failed", []):
        notices.discard_pending()
    data["_reading_minutes"] = max(1, (sum(len(embed.get("description", "")) for embed in embeds) + 499) // 500)
    data["_section_count"] = len(embeds)
    failures = get_failures()
    return [build_header(now, data, failures)] + embeds


def _scheduled_delivery_done(now: datetime) -> bool:
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return False
    try:
        with open(DELIVERY_STATE_PATH, encoding="utf-8") as state_file:
            state = json.load(state_file)
        return isinstance(state, dict) and state.get("last_successful_date") == now.date().isoformat()
    except (OSError, ValueError, TypeError):
        return False


def _mark_scheduled_delivery(now: datetime) -> None:
    if (os.environ.get("GITHUB_EVENT_NAME") != "schedule"
            or settings.env_bool("DISCORD_DRY_RUN") or settings.env_bool("BRIEF_READ_ONLY")):
        return
    state = {
        "last_successful_date": now.date().isoformat(),
        "sent_at": now.isoformat(),
    }
    os.makedirs(os.path.dirname(DELIVERY_STATE_PATH), exist_ok=True)
    temp_path = DELIVERY_STATE_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as state_file:
        json.dump(state, state_file, ensure_ascii=False, indent=2)
        state_file.write("\n")
    os.replace(temp_path, DELIVERY_STATE_PATH)


def main() -> None:
    now = datetime.now(KST)
    if _scheduled_delivery_done(now):
        print(f"{now.date().isoformat()} 브리핑은 이미 전송되어 중복 실행을 건너뜁니다.")
        return
    target = _scheduled_target(now)
    if target:
        # Start the runner early to absorb Actions cron delays, but collect
        # fresh data only shortly before delivery. Late recovery runs send now.
        print(f"[예약] {target:%Y-%m-%d %H:%M} KST 발송 · 07:57부터 수집", flush=True)
        _wait_until(target - timedelta(minutes=3))
        now = datetime.now(KST)
    notices.discard_pending()
    try:
        embeds = build_brief(now)
        if target:
            _wait_until(target)
        ds.send(embeds)
        notices.commit_pending()
    finally:
        notices.discard_pending()
    _mark_scheduled_delivery(datetime.now(KST))


if __name__ == "__main__":
    from briefing.cli import run
    raise SystemExit(run())
