"""공부 피드 섹션 — arXiv에서 관심 키워드에 걸리는 최신 논문 1편을 LLM이 요약.

개념/용어도 LLM이 그 논문에서 실제로 뽑는다(정적 목록 순환이 아님).
LLM이 없거나 실패하면 각각 자체 폴백으로 조용히 내려간다.
"""

from datetime import datetime

from sources import _arxiv, _llm
from sources._shared import KST, fail, tr

RESEARCH_FIELD = "Multimodal AI Reliability & Metacognition"
RESEARCH_KEYWORDS = [
    "vision language model",
    "confidence calibration",
    "visual state tracking",
    "hallucination",
    "video LLM",
    "metacognition",
    "uncertainty",
]
ARXIV_CATEGORIES = ["cs.CV", "cs.CL", "cs.LG"]

# LLM도 없고 그날 논문도 없을 때만 쓰는 최종 폴백 — 아주 드문 경우.
FALLBACK_CONCEPT = ("ECE (Expected Calibration Error)", "예측 confidence를 구간으로 나눠 평균 확신도와 실제 정확도 차이를 가중평균한 값. 0에 가까울수록 잘 보정됨.")
FALLBACK_TERMS = [
    ("ablation study", "구성요소를 하나씩 빼며 기여도를 검증하는 실험. 논문 후반부에 거의 필수"),
    ("inductive bias", "모델 구조에 내재된 가정. CNN의 지역성, Transformer의 순서 무관성이 대표 예"),
    ("zero-shot / few-shot", "학습 예시를 아예 안 주거나(zero-shot) 몇 개만 주고(few-shot) 바로 평가하는 세팅"),
]


def _paper_sections_via_llm(best):
    """LLM이 초록을 실제로 읽고 문제의식/방법/결과/한계/접점을 뽑는다.

    '내 연구와의 접점'도 이제 키워드 매칭이 아니라 LLM이 초록을 읽고
    판단한다 — 관련 없으면 억지로 엮지 말고 솔직하게 말하도록 프롬프트에
    명시해뒀다.
    """
    s = _llm.summarize_paper(best["title"], best["summary"], RESEARCH_FIELD, RESEARCH_KEYWORDS)
    return [
        ("문제의식", s["problem"]),
        ("방법", s["method"]),
        ("결과", s["result"]),
        ("한계", s["limitation"]),
        ("내 연구와의 접점", s["connection"]),
    ]


def _paper_sections_heuristic(best, matched):
    """LLM 실패 시 폴백 — 초록을 문장 위치로 잘라 배치하는 근사치.

    (문제의식=첫 문장, 방법=중간, 결과=끝 문장 — 논문 초록의 흔한 서술
    순서를 이용). 한계는 "however/limitation" 류 신호어가 있는 문장을
    찾아 쓰고, 없으면 정직하게 "명시 없음"이라고 표시한다. 접점은
    실제로 매칭된 키워드를 그대로 보여준다(추론 아님).
    """
    problem, method, result, limitation = _arxiv.split_sections(best["summary"])
    sections = [("문제의식", tr(problem))]
    if method:
        sections.append(("방법", tr(method, cap=220)))
    if result:
        sections.append(("결과", tr(result)))
    sections.append(("한계", tr(limitation) if limitation else "초록에 명시된 한계 없음 — 원문 참고"))
    sections.append((
        "내 연구와의 접점",
        f"키워드 매칭: {', '.join(matched)}" if matched else "카테고리 기준으로만 선정됨 (키워드 매칭 없음)",
    ))
    return sections


def _glossary(best):
    """오늘 논문에서 LLM이 실제로 뽑은 개념/용어. 없으면 최종 폴백 1세트."""
    if best:
        try:
            g = _llm.generate_glossary(best["title"], best["summary"])
            concept = (g["concept"]["name"], g["concept"]["desc"])
            terms = [(t["term"], t["desc"]) for t in g["terms"]]
            return concept, terms
        except Exception as e:
            print(f"[경고] 개념/용어 생성(LLM) 실패: {type(e).__name__}: {e}")
            fail("개념·용어(LLM)")
    return FALLBACK_CONCEPT, FALLBACK_TERMS


def get_study():
    """arXiv에서 관심 키워드에 걸리는 최신 논문 1편을 골라 LLM이 요약한다.

    LLM이 없거나 실패하면 초록을 문장 위치로 잘라 배치하는 근사치
    (_paper_sections_heuristic)로 조용히 폴백한다.
    """
    try:
        papers = _arxiv.search(RESEARCH_KEYWORDS, ARXIV_CATEGORIES, max_results=10)
        best, matched = _arxiv.pick_best(papers, RESEARCH_KEYWORDS)
    except Exception as e:
        print(f"[경고] arXiv 조회 실패: {type(e).__name__}: {e}")
        fail("arXiv 논문")
        best, matched = None, []

    if best:
        try:
            sections = _paper_sections_via_llm(best)
        except Exception as e:
            print(f"[경고] 논문 LLM 요약 실패: {type(e).__name__}: {e}")
            fail("논문 요약(LLM)")
            sections = _paper_sections_heuristic(best, matched)

        arxiv_id = best["url"].rstrip("/").rsplit("/", 1)[-1]
        authors = best["authors"]
        author_note = f"{authors[0]} 외 {len(authors) - 1}명" if len(authors) > 1 else (authors[0] if authors else "")
        paper_title = best["title"]
        paper_meta = f"arXiv:{arxiv_id}" + (f" · {author_note}" if author_note else "")
        paper_url = best["url"]
    else:
        paper_title = "(arXiv 조회 실패)"
        paper_meta = "잠시 후 다시 시도해주세요"
        paper_url = "https://arxiv.org"
        sections = []

    concept, terms = _glossary(best)

    return {
        "paper_title": paper_title,
        "paper_meta": paper_meta,
        "paper_url": paper_url,
        "paper_sections": sections,
        "concept": concept,
        "terms": terms,
    }
