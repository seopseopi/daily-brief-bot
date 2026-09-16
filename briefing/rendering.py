"""Discord presentation without I/O; rendering failures are recorded in data."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import discord_sender as ds
import settings
from sources._shared import KST, fail
from briefing.planning import assignment_is_overdue, plan_day

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def _footer(embed: dict, text: str, timestamp: datetime | None = None) -> dict:
    if text:
        embed["footer"] = {"text": text[:2048]}
    if timestamp:
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                timestamp = None
        if isinstance(timestamp, datetime):
            embed["timestamp"] = timestamp.isoformat()
    return embed


def _format_time(value: datetime | None) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return "시각 미상"
    return value.astimezone(KST).strftime("%H:%M") if isinstance(value, datetime) else "시각 미상"


def _assignment_line(days: int, name: str, note: str, today: date, now: datetime | None = None) -> str:
    due = today + timedelta(days=days)
    if days < 0:
        mark, label = "🚨", f"{abs(days)}일 연체"
    elif now is not None and assignment_is_overdue((days, name, note), now):
        mark, label = "🚨", "기한 지남"
    elif days == 0:
        mark, label = "🔴", "오늘 마감"
    elif days <= 2:
        mark, label = "🔴", f"D-{days}"
    elif days <= 7:
        mark, label = "🟡", f"D-{days}"
    else:
        mark, label = "🟢", f"D-{days}"
    line = f"{mark} **{label} · {due:%m/%d}**  {name}"
    if note:
        line += f"\n> {note}"
    return line


def _deterministic_highlights(now: datetime, data: dict) -> list[tuple[str, str]]:
    """Prioritize actions with code, not generative interpretation."""
    highlights = []
    schedule_data = data.get("schedule") or {}
    todo_items = data.get("assignments") or []
    weather_data = data.get("weather") or {}

    if schedule_data.get("status") in {"unavailable", "partial"}:
        highlights.append(("일정 소스 확인 필요", "연결된 일정 소스 오류로 오늘 일정이 완전하지 않을 수 있어요"))
    elif schedule_data.get("status") == "unconfigured":
        highlights.append(("개인 일정 미연결", "캘린더나 비공개 고정 시간표를 연결해야 오늘 일정을 확인할 수 있어요"))

    plan = plan_day(now, schedule_data, todo_items)
    overdue = plan["overdue"]
    due_today = [item for item in plan["due_soon"] if item[0] == 0]
    if overdue:
        detail = overdue[0][1]
        if due_today:
            detail += f" · 오늘 마감 {len(due_today)}개도 확인하세요"
        highlights.append((f"연체 과제 {len(overdue)}개", detail))
    elif due_today:
        highlights.append((f"오늘 마감 {len(due_today)}개", due_today[0][1]))

    if plan["conflicts"]:
        conflict = plan["conflicts"][0]
        highlights.append((f"일정 겹침 {conflict['start']:%H:%M}–{conflict['end']:%H:%M}",
                           " · ".join(conflict["names"])))
    if not overdue and not due_today and plan["due_soon"]:
        days, name, _note = plan["due_soon"][0]
        if days <= 2:
            highlights.append((f"미리 준비 · D-{days}", name))

    events = sorted(schedule_data.get("events") or [], key=lambda event: (event.get("all_day", False), event["start"]))
    timed = [event for event in events if not event.get("all_day")]
    active = [event for event in timed if event["start"] <= now < event["end"]]
    upcoming = [event for event in timed if event["start"] > now]
    all_day = [event for event in events if event.get("all_day") and event["start"] <= now < event["end"]]
    if active:
        event = active[0]
        when = "종일" if event["all_day"] else f"{event['end']:%H:%M} 종료"
        where = f" · {event['location']}" if event.get("location") else ""
        highlights.append((f"진행 중 · {when}", f"{event['name']}{where}"))
    elif upcoming:
        event = upcoming[0]
        when = "종일" if event["all_day"] else f"{event['start']:%H:%M}"
        where = f" · {event['location']}" if event.get("location") else ""
        highlights.append((f"다음 일정 {when}", f"{event['name']}{where}"))
    elif all_day:
        event = all_day[0]
        where = f" · {event['location']}" if event.get("location") else ""
        highlights.append(("오늘 종일 일정", f"{event['name']}{where}"))

    if weather_data.get("status") == "fresh":
        advice = " · ".join(weather_data["advice"])
        highlights.append((f"{weather_data['condition']} · 강수 {weather_data['rain_probability']}%", advice))

    news_items = data.get("news") or []
    if news_items:
        top = max(news_items, key=lambda item: item["published_at"])
        highlights.append(("최신 시사", f"{top['title']} · {top['publisher']} {_format_time(top['published_at'])}"))

    if not events and schedule_data.get("status") == "fresh":
        highlights.append(("오늘 등록된 일정 없음", schedule_data.get("source", "일정 소스 확인 완료")))

    if not highlights:
        # Optional-only briefs are valid: a market or study edition does not
        # need schedule/weather data to produce a successful header.
        render_failed = data.get("_render_failed", [])
        health = data.get("_source_health", {})
        checked = [section for section in ("notices", "market", "sports", "study", "community")
                   if section in data and data[section] is not None and section not in render_failed
                   and health.get(section, {}).get("status") != "unavailable"]
        if checked:
            labels = " · ".join(SECTION_LABELS[section] for section in checked)
            detail = f"{labels} 소식을 아래에서 확인하세요" if any(data[section] for section in checked) else f"{labels} 확인 완료 · 새로 표시할 항목이 없습니다"
            highlights.append(("오늘의 관심 소식", detail))

    return highlights[:3]


def build_header(now: datetime, data: dict, failures: list[str]) -> dict:
    date_text = f"{now.month}월 {now.day}일 {WEEKDAYS[now.weekday()]}요일"
    lines = []
    try:
        highlights = _deterministic_highlights(now, data)
    except (KeyError, TypeError, ValueError, AttributeError):
        highlights = [("핵심 요약 확인 필요", "일부 데이터 형식이 올바르지 않습니다. 아래 섹션별 상태를 확인하세요.")]
    for index, (title, detail) in enumerate(highlights, 1):
        lines.append(f"{['1️⃣', '2️⃣', '3️⃣'][index - 1]} **{title}**\n> {detail}")
    if not lines:
        lines.append("⚠️ **핵심 데이터를 불러오지 못했습니다**\n> 아래 실패 상태를 확인해주세요")
    if failures:
        lines.append(f"-# ⚠️ 조회 실패/부분 실패: {', '.join(failures)}")
    if data.get("_reading_minutes"):
        lines.append(f"-# 약 {data['_reading_minutes']}분 읽기 · {data['_section_count']}개 섹션 · 핵심 → 오늘 할 일 → 관심 소식")
    embed = ds.make_embed(f"📰 {date_text}", "\n\n".join(lines), "header")
    return _footer(embed, f"{now:%H:%M} KST 생성 · 일정 상태·마감·충돌·다음 일정 우선", now)


def build_weather(value: dict) -> dict:
    if value.get("status") != "fresh":
        body = f"**{value.get('location', '설정 위치')} 날씨를 불러오지 못했습니다.**\n> 외출 전 기상 정보를 따로 확인해주세요."
    else:
        air = value.get("air_quality")
        air_line = ""
        if air:
            air_line = (
                f"\n> 대기질 {air['label']} (US AQI {air['aqi']}) · "
                f"PM2.5 {air['pm2_5']:.1f} / PM10 {air['pm10']:.1f}㎍/㎥"
            )
        body = (
            f"**{value['location']} · {value['condition']} {value['temperature']:.1f}°C** "
            f"(체감 {value['apparent_temperature']:.1f}°C)\n"
            f"> 최저 {value['low']:.1f}° / 최고 {value['high']:.1f}° · "
            f"강수확률 최대 {value['rain_probability']}% · 바람 {value['wind_speed']:.1f}km/h"
            f"{air_line}\n\n"
            f"🧭 {' · '.join(value['advice'])}\n"
            f"-# [예보 출처]({value['source_url']})"
        )
        periods = value.get("periods", [])
        if periods:
            body += "\n\n**시간대별 외출 참고**\n" + "\n".join(
                f"• {period['label']} {period['start']:%H:%M}–{period['end']:%H:%M} · "
                f"{period['temperature_min']:.0f}–{period['temperature_max']:.0f}°C"
                + (f" · 강수 {period['rain_probability']}%" if period.get('rain_probability') is not None else "")
                for period in periods
            )
        rain = value.get("next_rain")
        if rain:
            until = f"{rain['end']:%H:%M}" if rain.get("end") else "종료 미확인"
            body += f"\n\n☂️ **강수 가능 시간** {rain['start']:%H:%M}–{until} · 구간 내 최대 {rain['probability']}%"
        if value.get("hourly_status") == "partial":
            body += "\n-# 시간별 예보 일부 누락 · 확인된 구간만 표시"
    embed = ds.make_embed("🌤️ 오늘 날씨 · 대기질 예보", body, "weather")
    source = f"{value.get('source', '날씨 소스')} · {_format_time(value.get('as_of'))} KST 기준"
    return _footer(embed, source, value.get("as_of"))


def build_schedule(schedule_data: dict, todo_items: list[tuple], now: datetime) -> dict:
    parts = []
    status = schedule_data.get("status")
    if status == "unavailable":
        parts.append("⚠️ **일정 소스 오류** — 아래 일정은 완전하지 않을 수 있습니다.")
    elif status == "partial":
        parts.append("⚠️ **일부 일정 소스만 정상 조회됨**")
    elif status == "unconfigured":
        parts.append("⚠️ **개인 일정 미연결** — 캘린더 또는 비공개 고정 시간표를 연결하세요.")
    elif not schedule_data.get("calendar_configured") and schedule_data.get("fixed_timetable_used"):
        parts.append("⚠️ **개인 캘린더 미연결** — 현재 고정 시간표만 표시합니다.")

    events = schedule_data.get("events") or []
    if not events and status not in {"unavailable", "unconfigured"}:
        parts.append("_캘린더에서 확인된 오늘 일정 없음_")
    for event in events:
        if event["all_day"]:
            time_text = "종일"
        else:
            time_text = f"{event['start']:%H:%M}–{event['end']:%H:%M}"
        block = f"**{time_text}**  {event['name']}"
        if event["end"] <= now:
            block += " · 종료"
        elif event["start"] <= now and not event.get("all_day"):
            block += " · 진행 중"
        if event.get("location"):
            block += f"\n> 📍 {event['location']}"
        parts.append(block)
    plan = plan_day(now, schedule_data, todo_items)
    if plan["conflicts"]:
        parts.append("**⚠️ 조정할 일정**\n" + "\n".join(
            f"• {conflict['start']:%H:%M}–{conflict['end']:%H:%M} · {' ↔ '.join(conflict['names'])}"
            for conflict in plan["conflicts"]
        ))
    if plan["free_slots"]:
        parts.append("**🕐 오늘 남은 빈 시간**\n" + "\n".join(
            f"• {slot['start']:%H:%M}–{slot['end']:%H:%M} · {slot['minutes']}분"
            for slot in plan["free_slots"]
        ) + "\n-# 등록된 일정 기준 · 이동·식사 시간은 별도 고려")
        if plan["focus_task"]:
            slot = plan["focus_slot"]
            task = plan["focus_task"]
            focus_end = plan["focus_end"]
            parts.append(f"**✍️ 먼저 시작할 일**\n{slot['start']:%H:%M}–{focus_end:%H:%M} · {task[1]} 준비\n"
                         "-# 마감순 제안 · 소요시간 추정이나 일정 등록은 하지 않습니다")
    elif status == "fresh":
        parts.append("🕐 오늘 남은 시간에 30분 이상 빈 구간 없음")

    parts.append("**📝 과제 · 마감**")
    if not todo_items:
        parts.append("_등록된 미완료 과제 없음_")
    else:
        for label, items in (
            ("지금 확인", [item for item in todo_items if item[0] <= 0]),
            ("이번 주 준비", [item for item in todo_items if 0 < item[0] <= 7]),
            ("미리 보기", [item for item in todo_items if item[0] > 7]),
        ):
            if items:
                parts.append(f"__{label} · {len(items)}개__\n" + "\n".join(
                    _assignment_line(days, name, note, now.date(), now)
                    for days, name, note in sorted(items, key=lambda item: (item[0], item[1]))
                ))

    embed = ds.make_embed("📅 오늘 일정 · 마감", "\n\n".join(parts), "schedule")
    return _footer(embed, f"{schedule_data.get('source', '일정 소스 미상')} · {now:%H:%M} KST 조회", now)


def build_notices(items, status="ok") -> dict:
    if not items:
        body = ("조회한 공지 목록에 새 공지가 없습니다." if status in {"ok", "fresh", "empty"}
                else "⚠️ 공지 소스 일부를 확인하지 못했습니다. 새 공지가 누락될 수 있습니다.")
        return _footer(ds.make_embed("🎓 새 학사 공지", body, "notice"),
                       "국민대 컴퓨터공학부 · SW중심대학")
    parts = []
    for label, posts in items:
        for title, url in posts:
            parts.append(f"**{label}**\n{title}\n-# [원문]({url})")
    return _footer(ds.make_embed("🎓 새 학사 공지", "\n\n".join(parts), "notice"), "국민대 컴퓨터공학부 · SW중심대학 직접 확인")


def _stock_lines(items) -> str:
    output = []
    for name, price, note in items:
        line = f"**{name}** {price}"
        if note:
            line += f"\n> {note}"
        output.append(line)
    return "\n".join(output)


def build_market(value: dict) -> dict:
    parts = [f"**🇰🇷 {value['kr_index']}**\n> {value['kr_note']}"]
    if value.get("kr_holdings"):
        parts.append(f"__보유 종목__\n{_stock_lines(value['kr_holdings'])}")
    if value.get("kr_hot"):
        parts.append(f"__실시간 관심 종목__\n{_stock_lines(value['kr_hot'])}")
    parts.append(f"**🇺🇸 {value['us_index']}**\n> {value['us_note']}")
    if value.get("us_holdings"):
        parts.append(f"__보유 종목__\n{_stock_lines(value['us_holdings'])}")
    if value.get("us_hot"):
        parts.append(f"__관심 목록__\n{_stock_lines(value['us_hot'])}")
    parts.append(f"💱 {value['fx']}")
    kr_signal, kr_detail = value["outlook_kr"]
    us_signal, us_detail = value["outlook_us"]
    parts.append(
        f"📘 **간밤 흐름** {kr_signal}\n> {kr_detail}\n"
        f"📙 **변동성 지표** {us_signal}\n> {us_detail}\n"
        "-# 관측값을 요약한 참고자료이며 예측·투자 조언이 아닙니다."
    )
    parts.append("-# [국내 시세 출처](https://stock.naver.com/) · [미국 시세 출처](https://finance.yahoo.com/)")
    as_of = value.get("as_of")
    source_note = value.get("source_note") or "네이버페이 증권 · Yahoo Finance"
    footer = f"{source_note} · {_format_time(as_of)} KST 조회"
    return _footer(ds.make_embed("📈 마켓", "\n\n".join(parts), "market"), footer, as_of)


def build_news(items: list[dict]) -> dict:
    if not items:
        body = "**신선한 기사 데이터를 불러오지 못했습니다.**\n> 오래되거나 발행시각이 없는 기사는 대신 싣지 않았습니다."
        return _footer(ds.make_embed("🗞️ 알아둘 시사", body, "news"), "최대 허용 기사 나이: 설정값 기준")
    lines = []
    for item in items:
        when = item["published_at"].astimezone(KST).strftime("%m/%d %H:%M")
        block = f"**{item['label']} · {item['publisher']} {when}**\n[{item['title']}]({item['url']})"
        if item.get("detail"):
            block += f"\n> {item['detail']}"
        related = item.get("related")
        if related:
            block += f"\n-# 관련 보도(사실검증 표시는 아님): [{related['publisher']}]({related['url']})"
        if item.get("summary_kind") == "ai_summary_of_publisher_lead":
            block += "\n-# 매체 리드문 기반 AI 압축 요약"
        lines.append(block)
    newest = max(item["published_at"] for item in items)
    return _footer(ds.make_embed("🗞️ 알아둘 시사", "\n\n".join(lines), "news"), f"발행시각 있는 최근 {settings.NEWS_MAX_AGE_HOURS}시간 기사만 · 원문 링크 제공", newest)


def build_sports(value: dict) -> dict:
    head, detail, standing, next_game = value["doosan"]
    body = (
        f"**{head}**\n> {detail}\n> {standing}\n> {next_game}\n\n"
        f"**⚽ 해외축구**\n> {value['football']}\n"
        "-# [경기 데이터 출처](https://sports.naver.com/)"
    )
    return _footer(ds.make_embed("⚾ 스포츠", body, "sports"), "네이버 스포츠 · 브리핑 생성 시 조회")


def build_study(value: dict) -> dict:
    parts = [f"**📄 오늘의 논문**\n[{value['paper_title']}]({value['paper_url']})\n-# {value['paper_meta']}"]
    for label, text in value["paper_sections"]:
        parts.append(f"**{label}**\n> {text}")
    if value.get("concept"):
        concept_name, concept_description = value["concept"]
        parts.append(f"**💡 개념 한 입 — {concept_name}**\n> {concept_description}")
    if value.get("terms"):
        terms = [f"`{term}`\n> {description}" for term, description in value["terms"]]
        parts.append("**🔤 오늘의 용어**\n" + "\n".join(terms))
    kind = value.get("summary_kind")
    footer = "arXiv 초록 기반 AI 요약 · 원문으로 재확인" if kind == "ai" else "arXiv 초록의 명시적 문장 발췌 · 자동 번역 실패 시 영어 원문 표시"
    return _footer(ds.make_embed("📚 공부 피드", "\n\n".join(parts), "study"), footer)


def build_community(items) -> dict:
    lines = []
    for item in items:
        if isinstance(item, dict):
            source = item.get("source") or item.get("label", "커뮤니티")
            kind = item.get("kind") or item.get("type") or "반응"
            stat = item.get("stat", "")
            title = item.get("title", "")
            detail = item.get("detail") or item.get("excerpt", "")
            url = item.get("url")
            published = item.get("published_at")
        else:
            source, stat, title, detail, url = item[:5]
            kind, published = None, None
        meta = " · ".join(part for part in (kind, stat, _format_time(published) if published else "") if part)
        block = f"**{source}** -# {meta}\n{title}"
        if detail:
            block += f"\n> {detail}"
        if url:
            block += f"\n-# [원문/토론 확인]({url})"
        lines.append(block)
    body = "\n\n".join(lines) or "최근 기준을 통과한 커뮤니티 글이 없습니다."
    body += "\n\n-# ⚠️ 커뮤니티 반응·정보글 후보입니다. 사실로 검증된 내용이 아니며 원문을 확인하세요."
    return _footer(ds.make_embed("💬 커뮤니티 반응 · 정보글", body, "community"), f"최근 {settings.COMMUNITY_MAX_AGE_HOURS}시간 · 공식 브리핑과 분리")


SECTION_LABELS = {
    "weather": "날씨", "schedule": "일정 · 마감", "notices": "학사 공지",
    "news": "시사", "market": "마켓", "sports": "스포츠",
    "study": "공부 피드", "community": "커뮤니티",
}


def render_sections(now: datetime, data: dict, *, compact: bool | None = None) -> list[dict]:
    """Render sections independently; one bad payload must not lose the brief."""
    compact = settings.BRIEF_MODE == "compact" if compact is None else compact
    values = dict(data)
    builders = {
        "weather": lambda: build_weather(values["weather"]),
        "schedule": lambda: build_schedule(values["schedule"], values.get("assignments", []), now),
        "notices": lambda: build_notices(values["notices"], data.get("_source_health", {}).get("notices", {}).get("status", "ok")),
        "news": lambda: build_news(values["news"]),
        "market": lambda: build_market(values["market"]),
        "sports": lambda: build_sports(values["sports"]),
        "study": lambda: build_study(values["study"]),
        "community": lambda: build_community(values["community"]),
    }
    embeds = []
    for section in settings.DEFAULT_SECTIONS:
        if section not in settings.ENABLED_SECTIONS:
            continue
        try:
            if compact and section in {"news", "community"}:
                values[section] = [dict(item, detail="", excerpt="") if isinstance(item, dict) else item
                                   for item in values[section]]
            elif compact and section == "study" and isinstance(values.get(section), dict):
                values[section] = dict(values[section], concept=None, terms=[])
            embed = builders[section]()
        except Exception as exc:
            print(f"[경고] {section} 표시 실패: {type(exc).__name__}")
            fail(f"{SECTION_LABELS[section]} 표시")
            data.setdefault("_render_failed", []).append(section)
            embed = _footer(ds.make_embed(
                f"⚠️ {SECTION_LABELS[section]}",
                "데이터를 불러오거나 표시하지 못했습니다. 원본 서비스에서 확인해주세요.",
                section), f"{now:%H:%M} KST 확인 · 다른 섹션은 계속 제공", now)
        if embed is not None:
            if section == "schedule" and data.get("_source_health", {}).get("assignments", {}).get("status") in {"unavailable", "partial"}:
                embed["description"] = "⚠️ **과제 조회 실패 · 마감 누락 가능**\n\n" + embed["description"].replace(
                    "_등록된 미완료 과제 없음_", "_과제 목록을 확인하지 못했습니다._")
            embeds.append(embed)
    return embeds
