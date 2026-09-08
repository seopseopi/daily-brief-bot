"""디시인사이드 + 레딧 공용 유틸리티 (stdlib만 사용).

get_community() 전용. 둘 다 비공식/문서화 안 된 접근(HTML 목록 파싱,
레딧 RSS)이라 사이트가 마크업을 바꾸면 조용히 깨질 수 있다 — 그래서
호출부가 갤러리/서브레딧 단위로 개별 fallback 처리한다.
"""

import html
import re
import urllib.request
import xml.etree.ElementTree as ET

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 8
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

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


def fetch_dc_top_post(gallery_id, minor=True):
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

        if not title or not href_m:
            continue
        posts.append({
            "title": title,
            "views": views,
            "replies": replies,
            "url": "https://gall.dcinside.com" + href_m.group(1),
        })

    posts.sort(key=lambda p: -p["views"])
    for p in posts:
        if _is_clean(p["title"]):
            return p
    return None


def fetch_reddit_top_post(subreddit):
    """서브레딧 top/.rss (오늘 기준) 1위 글. Reddit RSS엔 점수/댓글수가 없다."""
    url = f"https://www.reddit.com/r/{subreddit}/top/.rss?limit=5&t=day"
    raw = _get(url)
    root = ET.fromstring(raw)
    for entry in root.findall("a:entry", ATOM_NS):
        title = entry.find("a:title", ATOM_NS).text or ""
        if not _is_clean(title):
            continue
        link_el = entry.find("a:link", ATOM_NS)
        return {
            "title": title.strip(),
            "url": link_el.get("href") if link_el is not None else "",
        }
    return None
