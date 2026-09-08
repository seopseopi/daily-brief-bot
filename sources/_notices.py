"""국민대 컴공/SW 학사공지 파싱 (stdlib만 사용).

get_notices() 전용. 두 사이트 다 문서화 안 된 HTML 구조라 마크업이
바뀌면 조용히 깨질 수 있다 — 호출부가 사이트별 개별 fallback 처리.
"""

import html
import re
import urllib.request

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 10

CS_LIST_URL = "https://cs.kookmin.ac.kr/news/notice/"
CS_BASE = "https://cs.kookmin.ac.kr/news/notice/"
SW_LIST_URL = "https://software.kookmin.ac.kr/software/index.do"
SW_BASE = "https://software.kookmin.ac.kr/software/"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return res.read()


def fetch_cs_notices():
    """컴퓨터공학부 학사공지. 반환: [(id, title, url), ...] 최신순."""
    raw = _get(CS_LIST_URL).decode("utf-8", errors="replace")
    rows = re.findall(r'<td class="subject title">\s*<a href="\./(\d+)">([^<]+)</a>', raw)
    out = []
    for post_id, title in rows:
        clean_title = html.unescape(title).strip()
        out.append((post_id, clean_title, CS_BASE + post_id))
    return out


def fetch_sw_notices():
    """SW중심대학 공지사항. 반환: [(id, title, url), ...] 최신순."""
    raw = _get(SW_LIST_URL).decode("utf-8", errors="replace")
    rows = re.findall(
        r'<a href="bulletin/notice\.do\?mode=view&amp;articleNo=(\d+)"[^>]*>.*?'
        r'<span class="mini-title">\s*(?:\[공지\]\s*)?([^<]+?)\s*</span>',
        raw, re.S,
    )
    seen_ids = set()
    out = []
    for post_id, title in rows:
        if post_id in seen_ids:  # 페이지에 탭(전체/공지)이 중복 렌더링됨
            continue
        seen_ids.add(post_id)
        clean_title = html.unescape(title).strip()
        out.append((post_id, clean_title, f"{SW_BASE}bulletin/notice.do?mode=view&articleNo={post_id}"))
    return out
