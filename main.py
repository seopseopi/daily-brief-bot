"""아침 비서 - 매일 07:30 디스코드 브리핑 전송."""

from datetime import datetime, timedelta, timezone

import discord_sender as ds
from sources import dummy as src

KST = timezone(timedelta(hours=9))
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
DDAY_EMOJI = {0: "🔴", 1: "🔴", 2: "🟡", 3: "🟡", 4: "🟡"}


def dday_mark(days):
    return DDAY_EMOJI.get(days, "🟢")


def build_header(now, context_text):
    date_str = f"{now.month}월 {now.day}일 {WEEKDAYS[now.weekday()]}요일"
    lines = []
    for i, (title, detail) in enumerate(src.get_highlights(context_text), 1):
        num = ["1️⃣", "2️⃣", "3️⃣"][i - 1]
        lines.append(f"{num} **{title}**\n> {detail}")

    # 다른 섹션 + 방금 하이라이트 호출까지 쌓인 실패를 한 줄로 보여준다.
    # get_highlights()가 끝난 뒤에 모아야 그 실패도 포함된다.
    failures = src.get_failures()
    if failures:
        lines.append(f"-# ⚠️ 오늘 실패: {', '.join(failures)}")

    return ds.make_embed(f"📰 {date_str}", "\n\n".join(lines), "header")


def build_schedule():
    sc = src.get_schedule()
    parts = []
    for time_str, name, note in sc["events"]:
        block = f"**{time_str}**  {name}"
        if note:
            block += f"\n> {note}"
        parts.append(block)
    parts.append(f"🕐 **빈 시간**  {sc['free_slots']}")
    parts.append("\n**📝 과제**")
    assignments = src.get_assignments()
    if not assignments:
        parts.append("_없음_")
    for days, name, note in assignments:
        line = f"{dday_mark(days)} **D-{days}**  {name}"
        if note:
            line += f"\n> {note}"
        parts.append(line)
    return ds.make_embed("📅 일정 · 과제", "\n\n".join(parts), "schedule")


def build_notices():
    items = src.get_notices()
    if not items:
        body = "_새 공지 없음_"
    else:
        parts = []
        for label, posts in items:
            for title, url in posts:
                parts.append(f"**{label}**\n{title}\n-# [더보기]({url})")
        body = "\n\n".join(parts)
    return ds.make_embed("🎓 학사 공지", body, "notice")


def _stock_lines(items):
    out = []
    for name, price, note in items:
        out.append(f"**{name}** {price}\n> {note}")
    return "\n".join(out)


def build_market():
    m = src.get_market()
    p = []
    p.append(f"**🇰🇷 {m['kr_index']}**\n> {m['kr_note']}")
    p.append(f"__보유__\n{_stock_lines(m['kr_holdings'])}")
    p.append(f"__화제 종목__\n{_stock_lines(m['kr_hot'])}")
    p.append(f"**🇺🇸 {m['us_index']}**\n> {m['us_note']}")
    p.append(f"__보유__\n{_stock_lines(m['us_holdings'])}")
    p.append(f"__화제 종목__\n{_stock_lines(m['us_hot'])}")
    p.append(f"💱 {m['fx']}")
    ok, kn = m["outlook_kr"]
    ou, un = m["outlook_us"]
    p.append(
        f"📗 **국장** {ok}\n> {kn}\n"
        f"📙 **미장** {ou}\n> {un}\n"
        f"-# 컨센서스·야간선물 취합 참고자료 · 투자 조언 아님"
    )
    return ds.make_embed("📈 마켓", "\n\n".join(p), "market")


def build_news():
    lines = []
    for tag, title, detail, url in src.get_news():
        block = f"**{tag}** {title}\n> {detail}"
        if url:
            block += f"\n-# [더보기]({url})"
        lines.append(block)
    return ds.make_embed("🗞️ 뉴스", "\n\n".join(lines), "news")


def build_sports():
    s = src.get_sports()
    head, detail, standing, next_game = s["doosan"]
    body = f"**{head}**\n> {detail}\n> {standing}\n> {next_game}\n\n**⚽ 해외축구**\n> {s['football']}"
    return ds.make_embed("⚾ 스포츠", body, "sports")


def build_study():
    st = src.get_study()
    p = [f"**📄 오늘의 논문**\n[{st['paper_title']}]({st['paper_url']})\n-# {st['paper_meta']}"]
    for label, text in st["paper_sections"]:
        p.append(f"**{label}**\n> {text}")
    cname, cdesc = st["concept"]
    p.append(f"**💡 개념 한 입 — {cname}**\n> {cdesc}")
    term_lines = [f"`{t}`\n> {d}" for t, d in st["terms"]]
    p.append("**🔤 오늘의 용어**\n" + "\n".join(term_lines))
    return ds.make_embed("📚 공부 피드", "\n\n".join(p), "study")


def build_community():
    lines = []
    for source, stat, title, detail, url in src.get_community():
        block = f"**{source}** -# {stat}\n{title}\n> {detail}"
        if url:
            block += f"\n-# [더보기]({url})"
        lines.append(block)
    body = "\n\n".join(lines) + "\n\n-# 비공식 정보 · 논쟁 톤 제외하고 사실만 추출"
    return ds.make_embed("🔥 커뮤니티 펄스", body, "community")


def main():
    now = datetime.now(KST)

    # 헤더의 "오늘의 세 줄"은 다른 섹션 실제 내용을 LLM에 넘겨 요약하므로,
    # 나머지 섹션을 먼저 만들고 헤더를 맨 마지막에 조립한다.
    other_embeds = [
        build_schedule(),
        build_notices(),
        build_market(),
        build_news(),
        build_sports(),
        build_study(),
        build_community(),
    ]
    context_text = "\n\n".join(f"[{e['title']}]\n{e['description']}" for e in other_embeds)
    header_embed = build_header(now, context_text)

    ds.send([header_embed] + other_embeds)


if __name__ == "__main__":
    main()
