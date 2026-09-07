"""RSS 피드 공용 유틸리티 (stdlib만 사용).

get_news() 전용 헬퍼. LLM 없이도 동작하도록 각 기사의 RSS
<description>(매체가 직접 쓴 리드문)을 배경 설명으로 재사용한다 —
논평이 아니라 매체가 제공하는 사실 요약이라 "논평 제외 사실만" 요건에 맞는다.
"""

import html
import re
import urllib.request
import xml.etree.ElementTree as ET

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 8


def fetch_rss(url):
    """RSS 2.0 피드를 받아 [{title, link, description}, ...] 로 반환한다.

    실패 시 예외를 그대로 던진다 — 호출부(get_news 내부)에서
    카테고리별로 감싸 fallback 처리한다.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        raw = res.read()
    root = ET.fromstring(raw)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        desc = item.findtext("description") or ""
        items.append({
            "title": clean_text(title),
            "link": link.strip(),
            "description": clean_text(desc),
        })
    return items


def clean_text(text, max_len=None):
    """HTML 엔티티/잔여 태그를 제거하고 공백을 정리한다."""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_len and len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def title_tokens(title):
    """제목에서 2글자 이상 토큰만 뽑는다 (형태소 분석기 없이 쓰는 근사치)."""
    cleaned = re.sub(r"[\[\]()\"'…·,.!?%\-–—]", " ", title)
    return {t for t in cleaned.split() if len(t) >= 2}


def overlap_ratio(tokens_a, tokens_b):
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b))
