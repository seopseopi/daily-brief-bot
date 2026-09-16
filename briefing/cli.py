"""Send, preview, export and inspect setup from one command line."""

import argparse
from contextlib import contextmanager, redirect_stdout
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

import settings


def configuration_errors():
    errors = []
    if not settings.ENABLED_SECTIONS or settings.ENABLED_SECTIONS - set(settings.DEFAULT_SECTIONS):
        errors.append("BRIEF_SECTIONS에 유효한 섹션 이름을 지정하세요: " + ", ".join(settings.DEFAULT_SECTIONS))
    if settings.BRIEF_MODE not in {"full", "compact"}:
        errors.append("BRIEF_MODE는 full 또는 compact여야 합니다.")
    if "weather" in settings.ENABLED_SECTIONS:
        for name, value, limit in (("BRIEF_LATITUDE", settings.LOCATION_LATITUDE, 90),
                                   ("BRIEF_LONGITUDE", settings.LOCATION_LONGITUDE, 180)):
            raw = os.environ.get(name, "").strip()
            try:
                parsed = float(raw) if raw else value
                if not math.isfinite(parsed) or not -limit <= parsed <= limit:
                    raise ValueError
            except ValueError:
                errors.append(f"{name}에 올바른 좌표를 지정하세요.")
    return errors


def doctor():
    """Only report presence/validity; never print credential or personal values."""
    from sources.timetable_fixed import FIXED_TIMETABLE_ERROR
    checks = []

    def check(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    check("Discord 웹후크", "ready" if webhook else "error",
          "설정됨 · 실제 연결은 검사하지 않음" if webhook else "DISCORD_WEBHOOK_URL 필요 · demo/preview는 사용 가능")
    token = bool(os.environ.get("DISCORD_BOT_TOKEN", "").strip())
    channel = bool(os.environ.get("ASSIGNMENT_CHANNEL_ID", "").strip())
    check("과제 입력 채널", "ready" if token and channel else "error" if token != channel else "optional",
          "설정됨" if token and channel else "DISCORD_BOT_TOKEN과 ASSIGNMENT_CHANNEL_ID를 함께 설정")
    calendars = settings.CALENDAR_ICS_URLS
    try:
        valid_urls = all(urlparse(url).scheme in {"https", "http"} and urlparse(url).hostname for url in calendars)
    except ValueError:
        valid_urls = False
    fixed_configured = bool(settings.INCLUDE_FIXED_TIMETABLE and settings.FIXED_TIMETABLE_JSON)
    calendar_error = not valid_urls or (fixed_configured and FIXED_TIMETABLE_ERROR)
    check("개인 캘린더", "error" if calendar_error else "ready" if calendars or fixed_configured else "optional",
          "캘린더 주소 또는 고정 시간표 JSON 형식 확인" if calendar_error else
          "고정 시간표로 설정됨" if fixed_configured and not calendars else
          "설정됨 · 실제 연결은 검사하지 않음" if calendars else
          "CALENDAR_ICS_URLS 또는 FIXED_TIMETABLE_JSON 설정")
    check("고정 시간표", "error" if FIXED_TIMETABLE_ERROR else "ready" if settings.FIXED_TIMETABLE_JSON else "optional",
          "JSON 형식을 확인하세요" if FIXED_TIMETABLE_ERROR else "설정됨" if settings.FIXED_TIMETABLE_JSON else "FIXED_TIMETABLE_JSON 미설정")
    check("AI 요약", "ready" if os.environ.get("ANTHROPIC_API_KEY", "").strip() else "optional",
          "키 설정됨" if os.environ.get("ANTHROPIC_API_KEY", "").strip() else "키 없음 · 사실 데이터와 원문 기반 대체 출력 사용")
    for error in configuration_errors():
        check("브리핑 설정", "error", error)
    if not configuration_errors():
        check("브리핑 설정", "ready", "섹션·모드·좌표 형식 정상")
    return {"ok": all(item["status"] != "error" for item in checks), "checks": checks,
            "note": "설정 형식만 확인했습니다. 네트워크 요청·메시지 전송·상태 변경 없음."}


def _coverage(name, value):
    """Report actual content coverage without exposing titles or private values."""
    if isinstance(value, dict):
        if name == "schedule":
            return {"events": len(value.get("events", [])),
                    "calendar_connected": bool(value.get("calendar_configured") or value.get("fixed_timetable_used")),
                    "fixed_timetable_connected": bool(value.get("fixed_timetable_used"))}
        if name == "weather":
            return {"forecast": value.get("status") == "fresh", "air_quality": bool(value.get("air_quality")),
                    "periods": len(value.get("periods", []))}
        if name == "market":
            return {"kr_holdings": len(value.get("kr_holdings", [])),
                    "kr_holdings_configured": len(settings.MARKET_HOLDINGS_KR),
                    "us_holdings": len(value.get("us_holdings", [])),
                    "us_holdings_configured": len(settings.MARKET_HOLDINGS_US),
                    "kr_hot": len(value.get("kr_hot", [])), "us_hot": len(value.get("us_hot", []))}
        if name == "study":
            return {"paper": value.get("status") == "fresh", "concept": bool(value.get("concept")),
                    "terms": len(value.get("terms", [])), "summary_kind": value.get("summary_kind")}
    if isinstance(value, list):
        if name == "notices":
            return {"new_notices": sum(len(posts) for _, posts in value)}
        if name == "news":
            from sources.news import CATEGORIES
            return {"categories": len(value), "expected_categories": len(CATEGORIES)}
        if name == "assignments":
            return {"items": len(value), "channel_configured": bool(os.environ.get("DISCORD_BOT_TOKEN")
                                                                     and os.environ.get("ASSIGNMENT_CHANNEL_ID"))}
        if name == "community":
            return {"items": sum(bool(item[4]) for item in value)}
    return {}


def check_connections():
    """Exercise the configured sources without exporting their personal content."""
    from datetime import datetime
    from briefing.pipeline import collect_data
    from briefing.rendering import render_sections
    from sources import notices
    from sources._shared import KST, get_failures

    now = datetime.now(KST)
    get_failures()
    notices.discard_pending()
    try:
        data = collect_data(now)
        render_sections(now, data)
        sources = []
        for name, health in data.get("_source_health", {}).items():
            health = dict(health)
            if name in data.get("_render_failed", []):
                health["status"] = "unavailable"
            sources.append({"name": name, **health, "coverage": _coverage(name, data.get(name))})
        sources.sort(key=lambda source: source["name"])
        failures = get_failures()
        return {"ok": bool(sources) and not failures and all(source["status"] in {"ok", "fresh", "empty"} for source in sources),
                "checked_at": now.isoformat(), "sources": sources, "failures": failures,
                "optional_unconfigured": (["schedule"] if data.get("schedule", {}).get("status") == "unconfigured" else []),
                "note": "실제 소스 조회·표시 형식만 검사했습니다. Discord 메시지 전송·상태 저장 없음."}
    finally:
        notices.discard_pending()


@contextmanager
def _overrides(args):
    sections, mode = settings.ENABLED_SECTIONS, settings.BRIEF_MODE
    previous = {name: os.environ.get(name) for name in ("BRIEF_READ_ONLY", "DISCORD_DRY_RUN")}
    try:
        if args.sections:
            settings.ENABLED_SECTIONS = {part.strip() for part in re.split(r"[,;]", args.sections) if part.strip()}
        elif args.demo:
            settings.ENABLED_SECTIONS = set(settings.DEFAULT_SECTIONS)
        if args.compact:
            settings.BRIEF_MODE = "compact"
        elif args.demo:
            settings.BRIEF_MODE = "full"
        if args.preview or args.demo or args.check_connections:
            os.environ["BRIEF_READ_ONLY"] = "1"
            os.environ["DISCORD_DRY_RUN"] = "1"
        yield
    finally:
        settings.ENABLED_SECTIONS, settings.BRIEF_MODE = sections, mode
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def run(argv=None):
    parser = argparse.ArgumentParser(description="Daily Brief · 아침 브리핑 발송과 미리보기")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--preview", action="store_true", help="실제 소스를 조회하되 전송·상태 저장 없이 보기")
    action.add_argument("--demo", action="store_true", help="비밀키·네트워크 없이 가상 브리핑 보기")
    action.add_argument("--doctor", action="store_true", help="값을 노출하지 않고 설정 존재 여부·형식 확인")
    action.add_argument("--check-connections", action="store_true", help="실제 소스 연결을 내용 노출·전송·상태 저장 없이 검사")
    parser.add_argument("--format", choices=("text", "markdown", "json", "html"), default="text", help="미리보기 출력 형식")
    parser.add_argument("--output", type=Path, help="미리보기 저장 경로 (개인 데이터는 .private/ 권장)")
    parser.add_argument("--sections", help="표시할 섹션: weather,schedule,news 등")
    parser.add_argument("--compact", action="store_true", help="뉴스·커뮤니티 설명과 논문 용어를 접은 간결 모드")
    args = parser.parse_args(argv)
    if args.doctor and (args.output or args.format not in {"text", "json"}):
        parser.error("--doctor는 text/json 콘솔 출력만 지원합니다.")
    if args.check_connections and (args.output or args.format not in {"text", "json"}):
        parser.error("--check-connections는 text/json 콘솔 출력만 지원합니다.")
    if not (args.preview or args.demo or args.doctor or args.check_connections) and (args.output or args.format != "text"):
        parser.error("--format/--output은 --preview 또는 --demo와 함께 사용하세요.")

    with _overrides(args):
        if args.doctor:
            report = doctor()
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else
                  "\n".join(f"[{item['status']}] {item['name']}: {item['detail']}" for item in report["checks"]) + "\n" + report["note"])
            return 0 if report["ok"] else 1
        errors = [] if args.demo else configuration_errors()
        if args.demo and (not settings.ENABLED_SECTIONS or settings.ENABLED_SECTIONS - set(settings.DEFAULT_SECTIONS)):
            errors.append("--sections에 유효한 섹션 이름을 지정하세요.")
        if errors:
            parser.error(" ".join(errors))
        if args.check_connections:
            with redirect_stdout(sys.stderr):
                report = check_connections()
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else
                  "\n".join(f"[{source['status']}] {source['name']} · {source['duration_ms']}ms"
                            for source in report["sources"]) + "\n" + report["note"])
            return 0 if report["ok"] else 1
        import main
        if not (args.preview or args.demo):
            main.main()
            return 0
        from briefing.export import export_brief
        with redirect_stdout(sys.stderr):
            if args.demo:
                from briefing.demo import DEMO_NOW, demo_data
                from briefing.rendering import build_header, render_sections
                data = demo_data()
                sections = render_sections(DEMO_NOW, data)
                embeds = [build_header(DEMO_NOW, data, [])] + sections
                embeds[0]["description"] = "**🧪 데모 · 모든 일정·수치·소식은 가상 예시입니다.**\n\n" + embeds[0]["description"]
                for embed in embeds:
                    embed.setdefault("footer", {})["text"] = "가상 예시 · " + embed.get("footer", {}).get("text", "")
            else:
                embeds = main.build_brief()
            content = export_brief(embeds, args.format)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if not args.demo:
                # Personal previews are readable only by the current OS user.
                descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    os.chmod(args.output, 0o600)
                    output.write(content)
            else:
                args.output.write_text(content, encoding="utf-8")
            print(f"미리보기 저장: {args.output}", file=sys.stderr)
        else:
            print(content, end="")
    return 0
