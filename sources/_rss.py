"""RSS 피드 공용 유틸리티 (stdlib만 사용).

get_news() 전용 헬퍼. LLM 없이도 동작하도록 각 기사의 RSS
<description>(매체가 직접 쓴 리드문)을 배경 설명으로 재사용한다 —
논평이 아니라 매체가 제공하는 사실 요약이라 "논평 제외 사실만" 요건에 맞는다.
"""

import html
import re
import time
import urllib.error
import urllib.request

from http_client import open_url
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 8
ATTEMPTS = 2


def fetch_rss(url):
    """RSS 2.0 피드를 받아 기사와 발행시각/피드 출처를 반환한다.

    실패 시 예외를 그대로 던진다 — 호출부(get_news 내부)에서
    카테고리별로 감싸 fallback 처리한다.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    raw = None
    last_error = None
    for attempt in range(ATTEMPTS):
        try:
            with open_url(req, timeout=TIMEOUT) as res:
                raw = res.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        if attempt < ATTEMPTS - 1:
            time.sleep(0.5)
    if raw is None:
        raise last_error or RuntimeError("RSS request failed")
    fetched_at = datetime.now(timezone.utc)
    root = ET.fromstring(raw)
    channel = root.find("channel")
    source = clean_text(channel.findtext("title") or "") if channel is not None else ""
    items = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        desc = item.findtext("description") or ""
        published_text = item.findtext("pubDate") or item.findtext("date") or ""
        published_at = parse_datetime(published_text)
        items.append({
            "title": clean_text(title),
            "link": link.strip(),
            "description": clean_text(desc),
            "guid": clean_text(item.findtext("guid") or link),
            "published_at": published_at,
            "fetched_at": fetched_at,
            "source": source,
        })
    return items


def parse_datetime(value):
    """Parse an RFC 2822/ISO feed timestamp into an aware datetime."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


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
