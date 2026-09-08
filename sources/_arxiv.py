"""arXiv API 공용 유틸리티 (stdlib만 사용).

get_study() 전용. 요약을 LLM으로 재작성하는 대신, 초록을 문장 위치
기준으로 잘라 문제의식/방법/결과 자리에 배치한다 — 흔한 논문 초록의
"배경→접근→결과" 서술 순서를 그대로 이용하는 근사치라 완벽하진 않다.
"""

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 10
NS = {"a": "http://www.w3.org/2005/Atom"}

LIMITATION_SIGNALS = (
    "however", "limitation", "limited", "still", "remain", "future work",
    "despite", "challenge", "fail", "struggle", "drawback",
)


def search(keywords, categories, max_results=15):
    """제목/초록에 keywords 중 하나라도 걸리고, categories 중 하나에 속하는
    최신 논문을 최대 max_results개 가져온다."""
    cat_clause = " OR ".join(f"cat:{c}" for c in categories)
    kw_clause = " OR ".join(f'abs:"{k}"' for k in keywords)
    query = f"({cat_clause}) AND ({kw_clause})"
    url = (
        "http://export.arxiv.org/api/query?"
        + urllib.parse.urlencode({
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        })
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        raw = res.read()
    root = ET.fromstring(raw)
    papers = []
    for entry in root.findall("a:entry", NS):
        papers.append({
            "title": " ".join(entry.find("a:title", NS).text.split()),
            "summary": " ".join(entry.find("a:summary", NS).text.split()),
            "url": entry.find("a:id", NS).text.strip(),
            "authors": [a.find("a:name", NS).text for a in entry.findall("a:author", NS)],
        })
    return papers


def pick_best(papers, keywords):
    """키워드 매칭 개수가 가장 많은 논문을 고른다 (동률이면 더 최신 것 = 리스트 앞쪽)."""
    if not papers:
        return None, []

    def match_count(paper):
        text = (paper["title"] + " " + paper["summary"]).lower()
        return sum(1 for k in keywords if k.lower() in text or k.lower().replace(" ", "-") in text)

    scored = [(match_count(p), i, p) for i, p in enumerate(papers)]
    scored.sort(key=lambda x: (-x[0], x[1]))
    best = scored[0][2]
    text = (best["title"] + " " + best["summary"]).lower()
    matched = [k for k in keywords if k.lower() in text or k.lower().replace(" ", "-") in text]
    return best, matched


def split_sections(summary):
    """초록을 문장 단위로 잘라 (문제의식, 방법, 결과, 한계) 영어 원문 조각으로 나눈다."""
    sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
    sentences = [s for s in sentences if s]
    if not sentences:
        return "", "", "", ""

    problem = sentences[0]
    result = sentences[-1] if len(sentences) > 1 else ""
    method_sentences = sentences[1:-1] if len(sentences) > 2 else []
    method = " ".join(method_sentences)

    # 문제의식(첫 문장)과 안 겹치게, 그 뒤 문장에서만 한계 신호어를 찾는다.
    # 방법 문장이 있으면 거기서 우선 찾고, 없으면 첫 문장 이후 전체에서 찾는다.
    search_pool = method_sentences if method_sentences else sentences[1:]
    limitation = ""
    for s in search_pool:
        if any(sig in s.lower() for sig in LIMITATION_SIGNALS):
            limitation = s
            break

    return problem, method, result, limitation
