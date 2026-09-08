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


def fetch_dc_post_excerpt(post_url, max_len=140):
    """DC 상세페이지의 JSON-LD articleBody(검색용 요약, 이미 짧게 잘려있음)를 발췌로 쓴다.

    글 목록에는 본문이 없어서 상세페이지를 한 번 더 열어야 한다 — 선택된
    글에만(보통 3개) 호출하니 부담이 크지 않다. 못 찾으면 빈 문자열.
    """
    raw = _get(post_url).decode("utf-8", errors="replace")
    m = re.search(r'"articleBody":"(.*?)",\s*\n?\s*"keywords"', raw, re.S)
    if not m:
        return ""
    body = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
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
        content_el = entry.find("a:content", ATOM_NS)
        return {
            "title": title.strip(),
            "url": link_el.get("href") if link_el is not None else "",
            "excerpt": _reddit_excerpt_from_content(content_el.text if content_el is not None else ""),
        }
    return None
