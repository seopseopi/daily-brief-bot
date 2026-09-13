"""Fresh, source-attributed current-affairs headlines.

This module deliberately keeps the publisher-written headline and lead. An LLM
is not allowed to add background facts; factual compression belongs downstream
and remains opt-in. "Related coverage" means title-level topic similarity, not
fact-checking, and is labelled as such.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import settings
from sources import _llm, _rss
from sources._shared import KST, fail

YONHAP_POLITICS = "https://www.yna.co.kr/rss/politics.xml"
YONHAP_ECONOMY = "https://www.yna.co.kr/rss/economy.xml"
YONHAP_SOCIETY = "https://www.yna.co.kr/rss/society.xml"
YONHAP_INTERNATIONAL = "https://www.yna.co.kr/rss/international.xml"
YONHAP_CULTURE = "https://www.yna.co.kr/rss/culture.xml"
HANKYUNG_POLITICS = "https://www.hankyung.com/feed/politics"
HANKYUNG_IT = "https://www.hankyung.com/feed/it"

DETAIL_MAX_LEN = 180
FUTURE_TOLERANCE = timedelta(minutes=20)
CATEGORIES = (
    ("🏛️ 정치", YONHAP_POLITICS, "연합뉴스"),
    ("💼 경제", YONHAP_ECONOMY, "연합뉴스"),
    ("🏙️ 사회", YONHAP_SOCIETY, "연합뉴스"),
    ("🌏 국제", YONHAP_INTERNATIONAL, "연합뉴스"),
    ("🔬 과기", HANKYUNG_IT, "한국경제"),
    ("🎬 문화", YONHAP_CULTURE, "연합뉴스"),
)


def _fresh(items: list[dict], now: datetime) -> list[dict]:
    oldest = now - timedelta(hours=settings.NEWS_MAX_AGE_HOURS)
    result = []
    for item in items:
        published = item.get("published_at")
        if not published or not item.get("title") or not item.get("link"):
            continue
        published = published.astimezone(KST)
        if oldest <= published <= now + FUTURE_TOLERANCE:
            item = dict(item)
            item["published_at"] = published
            result.append(item)
    return sorted(result, key=lambda item: item["published_at"], reverse=True)


def _read_category(
    label: str,
    feed_url: str,
    publisher: str,
    now: datetime,
    excluded_urls: set[str] | None = None,
) -> dict:
    candidates = _fresh(_rss.fetch_rss(feed_url), now)
    if excluded_urls:
        candidates = [item for item in candidates if item["link"] not in excluded_urls]
    if not candidates:
        raise RuntimeError("no fresh timestamped article")
    top = candidates[0]
    lead = _rss.clean_text(top["description"], DETAIL_MAX_LEN)
    return {
        "label": label,
        "title": top["title"],
        "detail": lead or "요약은 원문에서 확인하세요.",
        "url": top["link"],
        "publisher": publisher,
        "published_at": top["published_at"],
        "related": None,
        "summary_kind": "publisher_lead" if lead else "headline_only",
        "status": "fresh",
    }


def _add_related_politics(primary: dict, now: datetime) -> None:
    """Attach a genuinely similar second headline without calling it verified."""
    try:
        other_items = _fresh(_rss.fetch_rss(HANKYUNG_POLITICS), now)[:12]
    except Exception:
        return
    primary_tokens = _rss.title_tokens(primary["title"])
    best = None
    best_score = 0.0
    for item in other_items:
        other_tokens = _rss.title_tokens(item["title"])
        common = primary_tokens & other_tokens
        score = _rss.overlap_ratio(primary_tokens, other_tokens)
        # Requiring two shared content tokens avoids one generic word being
        # presented as independent corroboration.
        if len(common) >= 2 and score > best_score:
            best, best_score = item, score
    if best is not None and best_score >= 0.45:
        primary["related"] = {
            "publisher": "한국경제",
            "title": best["title"],
            "url": best["link"],
            "published_at": best["published_at"],
        }


def get_news(now: datetime | None = None) -> list[dict]:
    now = (now or datetime.now(KST)).astimezone(KST)
    results = []
    seen_urls = set()
    for label, feed_url, publisher in CATEGORIES:
        try:
            item = _read_category(label, feed_url, publisher, now, seen_urls)
            results.append(item)
            seen_urls.add(item["url"])
        except Exception as exc:
            print(f"[경고] 뉴스 {label} 조회 실패: {type(exc).__name__}")
            fail(f"뉴스-{label.split()[-1]}")

    politics = next((item for item in results if item["label"] == "🏛️ 정치"), None)
    if politics:
        _add_related_politics(politics, now)

    if settings.USE_LLM_NEWS_SUMMARIES and results:
        try:
            prompts = [
                {"label": item["label"], "title": item["title"], "lead": item["detail"]}
                for item in results
            ]
            summaries = _llm.explain_news(prompts)
            for item, summary in zip(results, summaries):
                item["detail"] = summary
                item["summary_kind"] = "ai_summary_of_publisher_lead"
        except Exception as exc:
            print(f"[경고] 뉴스 요약(LLM) 실패: {type(exc).__name__}")
            fail("뉴스 요약(LLM)")

    return results
