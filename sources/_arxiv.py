"""arXiv API 공용 유틸리티 (stdlib만 사용).

get_study() 전용. 요약을 LLM으로 재작성하는 대신, 초록을 문장 위치
기준으로 잘라 문제의식/방법/결과 자리에 배치한다 — 흔한 논문 초록의
"배경→접근→결과" 서술 순서를 그대로 이용하는 근사치라 완벽하진 않다.
"""

import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 25
RETRIES = 2
RETRY_BACKOFF = 3
NS = {"a": "http://www.w3.org/2005/Atom"}

LIMITATION_SIGNALS = (
    "however", "limitation", "limited", "future work",
    "despite", "challenge", "fail", "struggle", "drawback",
)
RESULT_SIGNALS = (
    "we show", "we find", "we demonstrate", "our results", "results show",
    "achieves", "outperform", "improves", "we observe", "experiments show",
)
METHOD_SIGNALS = (
    "we propose", "we introduce", "we present", "our method", "our approach",
    "we develop", "we use", "we train",
)


def search(keywords, categories, max_results=15):
    """제목/초록에 keywords 중 하나라도 걸리고, categories 중 하나에 속하는
    최신 논문을 최대 max_results개 가져온다."""
    cat_clause = " OR ".join(f"cat:{c}" for c in categories)
    kw_clause = " OR ".join(f'abs:"{k}"' for k in keywords)
    query = f"({cat_clause}) AND ({kw_clause})"
    url = (
        "https://export.arxiv.org/api/query?"
        + urllib.parse.urlencode({
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        })
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    raw = None
    last_exc = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                raw = res.read()
            break
        except (urllib.error.URLError, TimeoutError) as e:
            # 429(요청 과다)나 타임아웃은 대개 일시적 — 잠깐 쉬고 재시도.
            last_exc = e
            if attempt < RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
    if raw is None:
        raise last_exc
    root = ET.fromstring(raw)
    papers = []
    for entry in root.findall("a:entry", NS):
        papers.append({
            "title": " ".join(entry.find("a:title", NS).text.split()),
            "summary": " ".join(entry.find("a:summary", NS).text.split()),
            "url": entry.find("a:id", NS).text.strip().replace("http://", "https://", 1),
            "authors": [a.find("a:name", NS).text for a in entry.findall("a:author", NS)],
            "published_at": _atom_datetime(entry.findtext("a:published", default="", namespaces=NS)),
            "updated_at": _atom_datetime(entry.findtext("a:updated", default="", namespaces=NS)),
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
    """초록 문장에서 명시적 신호어로 문제/방법/결과/한계를 찾는다.

    신호어가 없으면 빈 값을 반환한다. 마지막 문장을 무조건 '결과'로
    간주하면 코드 공개나 향후 계획을 연구 결과로 오인할 수 있기 때문이다.
    """
    sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
    sentences = [s for s in sentences if s]
    if not sentences:
        return "", "", "", ""

    problem = sentences[0]
    remaining = sentences[1:]
    method = next((sentence for sentence in remaining if any(sig in sentence.lower() for sig in METHOD_SIGNALS)), "")
    result = next((sentence for sentence in remaining if any(sig in sentence.lower() for sig in RESULT_SIGNALS)), "")

    # 문제의식(첫 문장)과 안 겹치게, 그 뒤 문장에서만 한계 신호어를 찾는다.
    # 방법 문장이 있으면 거기서 우선 찾고, 없으면 첫 문장 이후 전체에서 찾는다.
    search_pool = remaining
    limitation = ""
    for s in search_pool:
        if any(sig in s.lower() for sig in LIMITATION_SIGNALS):
            limitation = s
            break

    return problem, method, result, limitation


def _atom_datetime(value):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
