"""커뮤니티 소스 수집 유틸리티 (stdlib만 사용).

DC/Reddit 게시글은 커뮤니티의 *반응 신호*일 뿐 사실 출처가 아니다.
Hacker News도 공식 API에서 점수/댓글/게시 시각은 신뢰할 수 있지만, 링크된
글의 주장을 검증해 주는 것은 아니다. 호출부는 이 구분을 사용자에게 그대로
표시한다.

모든 fetch 함수는 가능한 한 같은 메타데이터 계약을 지킨다::

    {
        "title": str,
        "url": str,
        "published_at": timezone-aware datetime,
        "score": int | None,
        "comments": int | None,
        "views": int | None,
        "excerpt": str,
        "source_kind": "dc" | "reddit" | "hn",
        "signal_type": "정보 링크" | "반응 신호",
    }

게시 시각을 확인할 수 없거나 freshness window를 벗어난 글은 반환하지 않는다.
"""

import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 8
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
DEFAULT_MAX_AGE_HOURS = 24
KST = timezone(timedelta(hours=9))
HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_CANDIDATE_LIMIT = 20

# 완벽한 필터는 불가능 — 명백히 자극적/혐오성인 단어만 최소한으로 걸러낸다.
# 걸리면 해당 갤러리에서 다음 순위 글로 넘어간다 (통째로 스킵하지 않음).
BLOCKLIST = ("시발", "병신", "지랄", "새끼", "fuck", "nigger", "retard")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return res.read()


def _is_clean(title):
    low = title.lower()
    return not any(bad in title or bad in low for bad in BLOCKLIST)


def _parse_datetime(value, default_timezone=timezone.utc):
    """ISO-8601 문자열을 UTC datetime으로 정규화한다. 실패하면 None."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_timezone)
    return parsed.astimezone(timezone.utc)


def is_fresh(published_at, max_age_hours=DEFAULT_MAX_AGE_HOURS, now=None):
    """게시물이 freshness window 안인지 확인한다.

    원본 시각이 없으면 최신이라고 추측하지 않는다. 제공자/로컬 시계의 작은
    오차는 허용하되 5분보다 먼 미래 시각은 잘못된 데이터로 간주한다.
    """
    if not isinstance(published_at, datetime) or published_at.tzinfo is None:
        return False
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = now.astimezone(timezone.utc) - published_at.astimezone(timezone.utc)
    return timedelta(minutes=-5) <= age <= timedelta(hours=max_age_hours)


def fetch_dc_top_post(gallery_id, minor=True, max_age_hours=DEFAULT_MAX_AGE_HOURS, now=None):
    """갤러리 목록에서 공지 제외, 조회수 상위 중 첫 '클린'한 글 하나.

    minor=True면 마이너 갤러리(mgallery) 경로, False면 정식 갤러리.
    """
    board = "mgallery/board/lists" if minor else "board/lists"
    url = f"https://gall.dcinside.com/{board}?id={gallery_id}"
    raw = _get(url).decode("utf-8", errors="replace")

    row_starts = [m.start() for m in re.finditer(r'<tr class="ub-content us-post"', raw)]
    row_starts.append(len(raw))

    posts = []
    for i in range(len(row_starts) - 1):
        block = raw[row_starts[i]:row_starts[i + 1]]
        dtype_m = re.search(r'data-type="([^"]+)"', block)
        if not dtype_m or dtype_m.group(1) == "icon_notice":
            continue
        tit_m = re.search(r'<td class="gall_tit ub-word">(.*?)</td>', block, re.S)
        if not tit_m:
            continue
        tit_html = tit_m.group(1)
        href_m = re.search(r'href="([^"]+)"', tit_html)
        raw_text = html.unescape(re.sub(r"<[^>]+>", "", tit_html))
        collapsed = re.sub(r"\s+", " ", raw_text).strip()
        reply_m = re.search(r"\[(\d+)\]$", collapsed)
        title = collapsed[: reply_m.start()].strip() if reply_m else collapsed
        replies = int(reply_m.group(1)) if reply_m else 0

        count_m = re.search(r'<td class="gall_count">([^<]+)</td>', block)
        views = int(count_m.group(1)) if count_m and count_m.group(1).strip().isdigit() else 0

        date_m = re.search(r'<td class="gall_date"[^>]*title="([^"]+)"', block)
        published_at = _parse_datetime(date_m.group(1), KST) if date_m else None

        if not title or not href_m or not is_fresh(published_at, max_age_hours, now):
            continue
        posts.append({
            "title": title,
            "views": views,
            "replies": replies,
            "comments": replies,
            "score": None,
            "published_at": published_at,
            "excerpt": "",
            "source_kind": "dc",
            "signal_type": "반응 신호",
            "url": urljoin("https://gall.dcinside.com", href_m.group(1)),
        })

    posts.sort(key=lambda p: -p["views"])
    for p in posts:
        if _is_clean(p["title"]):
            return p
    return None


def fetch_dc_post_excerpt(post_url, max_len=140):
    """Extract visible post text, never the gallery-wide JSON-LD description."""
    raw = _get(post_url).decode("utf-8", errors="replace")
    m = re.search(
        r'<div\s+class="write_div"[^>]*>(.*?)</div>\s*(?:<script|</div>)',
        raw,
        re.S | re.I,
    )
    if not m:
        return ""
    body_html = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", m.group(1), flags=re.S | re.I)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body_html))
    body = re.sub(r"\s+", " ", body).strip()
    if len(body) > max_len:
        body = body[: max_len - 1].rstrip() + "…"
    return body


def _reddit_excerpt_from_content(content_html):
    """레딧 목록 RSS의 content 필드에서 '자체 글' 본문만 최대한 걸러낸다.

    이미지/링크 글은 썸네일+링크뿐이라 걸러내면 빈 문자열이 되고, 그 경우
    호출부가 요약 없음으로 처리한다. 레딧에 추가 요청을 안 보내려고
    이미 받은 응답만 재활용한다 — 레딧은 이미 IP 차단이 잦아서 요청을
    늘리고 싶지 않다.
    """
    if not content_html:
        return ""
    text = content_html
    text = re.sub(r"<img[^>]*>", " ", text)
    text = re.sub(r"<a[^>]*>\s*\[link\]\s*</a>", " ", text, flags=re.I)
    text = re.sub(r"<a[^>]*>\s*\[comments\]\s*</a>", " ", text, flags=re.I)
    text = re.sub(r"submitted by", " ", text, flags=re.I)
    text = re.sub(r"<a[^>]*>\s*/u/[^<]*</a>", " ", text)
    text = re.sub(r"<table>|</table>|<tr>|</tr>|<td>|</td>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) > 10 else ""


def fetch_reddit_top_post(subreddit, max_age_hours=DEFAULT_MAX_AGE_HOURS, now=None):
    """서브레딧 top RSS에서 freshness window 안의 첫 글을 반환한다.

    Reddit RSS는 점수/댓글 수를 제공하지 않으므로 값을 꾸며내지 않고 None으로
    보존한다. 게시 시각은 entry의 published(없으면 updated)를 사용한다.
    """
    url = f"https://www.reddit.com/r/{subreddit}/top/.rss?limit=5&t=day"
    raw = _get(url)
    root = ET.fromstring(raw)
    for entry in root.findall("a:entry", ATOM_NS):
        title = entry.find("a:title", ATOM_NS).text or ""
        if not _is_clean(title):
            continue
        published_el = entry.find("a:published", ATOM_NS)
        updated_el = entry.find("a:updated", ATOM_NS)
        published_text = (
            published_el.text if published_el is not None else
            updated_el.text if updated_el is not None else ""
        )
        published_at = _parse_datetime(published_text)
        if not is_fresh(published_at, max_age_hours, now):
            continue
        link_el = entry.find("a:link", ATOM_NS)
        content_el = entry.find("a:content", ATOM_NS)
        return {
            "title": title.strip(),
            "url": link_el.get("href") if link_el is not None else "",
            "excerpt": _reddit_excerpt_from_content(content_el.text if content_el is not None else ""),
            "published_at": published_at,
            "score": None,
            "comments": None,
            "views": None,
            "source_kind": "reddit",
            "signal_type": "반응 신호",
        }
    return None


def _hn_excerpt(text, max_len=280):
    """Ask HN 등의 HTML 본문을 짧은 plain text로 만든다."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", html.unescape(text))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def fetch_hn_top_post(max_age_hours=DEFAULT_MAX_AGE_HOURS, now=None,
                      candidate_limit=HN_CANDIDATE_LIMIT):
    """Hacker News 공식 Firebase API의 최신 top story 한 건.

    topstories의 순위를 유지하면서 오래됐거나 삭제된 항목을 건너뛴다. 외부
    링크가 있는 story는 ``정보 링크``로, Ask HN처럼 HN 자체 토론인 항목은
    ``반응 신호``로 분류한다. 어느 쪽도 내용의 사실성을 보증하진 않는다.
    """
    story_ids = json.loads(_get(f"{HN_API_BASE}/topstories.json"))
    for story_id in story_ids[:candidate_limit]:
        item = json.loads(_get(f"{HN_API_BASE}/item/{story_id}.json"))
        if not item or item.get("type") != "story" or item.get("deleted") or item.get("dead"):
            continue
        title = str(item.get("title") or "").strip()
        published_at = datetime.fromtimestamp(item["time"], timezone.utc) if item.get("time") else None
        if not title or not _is_clean(title) or not is_fresh(published_at, max_age_hours, now):
            continue

        discussion_url = f"https://news.ycombinator.com/item?id={story_id}"
        external_url = str(item.get("url") or "").strip()
        return {
            "title": title,
            "url": external_url or discussion_url,
            "discussion_url": discussion_url,
            "excerpt": _hn_excerpt(item.get("text", "")),
            "published_at": published_at,
            "score": int(item.get("score", 0)),
            "comments": int(item.get("descendants", 0)),
            "views": None,
            "source_kind": "hn",
            "signal_type": "정보 링크" if external_url else "반응 신호",
        }
    return None
