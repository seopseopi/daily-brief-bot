"""뉴스 섹션 — 연합뉴스/한경 RSS 최신 1건씩. 정치는 두 매체 교차확인.

반환 튜플은 (라벨, 제목, 배경설명, 링크, 소식통표시) 5개.
"소식통표시"는 정치 카테고리에서만 쓰는 "연합뉴스·한경 동시 보도" /
"단일 매체 확인" 마커 — LLM이 배경설명(detail)을 덮어써도 이 필드는
따로 있어서 안 사라진다 (예전엔 detail 문자열 안에 섞어놨다가 LLM
배경설명으로 통째로 덮어써서 사라지는 회귀가 있었음).
"""

from sources import _llm, _rss
from sources._shared import fail

YONHAP_POLITICS = "https://www.yna.co.kr/rss/politics.xml"
YONHAP_SOCIETY = "https://www.yna.co.kr/rss/society.xml"
YONHAP_INTERNATIONAL = "https://www.yna.co.kr/rss/international.xml"
YONHAP_CULTURE = "https://www.yna.co.kr/rss/culture.xml"
HANKYUNG_POLITICS = "https://www.hankyung.com/feed/politics"
HANKYUNG_IT = "https://www.hankyung.com/feed/it"  # 연합뉴스엔 IT/과학 전용 피드가 없음

CROSSCHECK_THRESHOLD = 0.34  # 제목 토큰 겹침 비율 — 이 이상이면 "동시 보도"로 간주
DETAIL_MAX_LEN = 140


def _single_category(label, feed_url, fallback_note):
    """한 매체·한 카테고리에서 최신 1건을 뽑는다. 실패 시 예외를 던진다."""
    items = _rss.fetch_rss(feed_url)
    if not items:
        raise RuntimeError("empty feed")
    top = items[0]
    detail = _rss.clean_text(top["description"], DETAIL_MAX_LEN) or fallback_note
    return [label, top["title"], detail, top["link"], ""]


def _politics_crosschecked():
    """정치는 연합뉴스·한경 두 매체 제목을 비교해 겹치는 이슈를 우선 채택한다.

    형태소 분석기 없이 쓰는 근사치 교차검증이라, 실패하면 조용히
    단일 매체(연합뉴스) 1건으로 낮춰서 보여준다 — 논평 없이 사실만.
    """
    try:
        yh_items = _rss.fetch_rss(YONHAP_POLITICS)[:8]
    except Exception:
        yh_items = []
    try:
        hk_items = _rss.fetch_rss(HANKYUNG_POLITICS)[:8]
    except Exception:
        hk_items = []

    if not yh_items and not hk_items:
        raise RuntimeError("정치 RSS 둘 다 실패")

    if yh_items and hk_items:
        best, best_score = None, 0.0
        for y in yh_items:
            y_tokens = _rss.title_tokens(y["title"])
            for h in hk_items:
                score = _rss.overlap_ratio(y_tokens, _rss.title_tokens(h["title"]))
                if score > best_score:
                    best_score, best = score, y
        if best and best_score >= CROSSCHECK_THRESHOLD:
            detail = _rss.clean_text(best["description"], DETAIL_MAX_LEN) or "연합뉴스·한경 동시 보도"
            return ["🏛️ 정치", best["title"], detail, best["link"], "연합뉴스·한경 동시 보도"]

    top = yh_items[0] if yh_items else hk_items[0]
    detail = _rss.clean_text(top["description"], DETAIL_MAX_LEN) or "단일 매체 확인"
    return ["🏛️ 정치", top["title"], detail, top["link"], "단일 매체 확인"]


def get_news():
    """각 카테고리는 독립적으로 fallback 처리한다 — 하나가 실패해도
    나머지 카테고리는 정상 출력되고, 브리핑 전체는 깨지지 않는다.

    조회에 성공한 카테고리들은 한 번의 LLM 호출로 "왜 중요한지" 배경
    설명을 받아 detail을 덮어쓴다. LLM이 없거나 실패하면 RSS 리드문을
    그대로 쓴다.
    """
    results = []
    try:
        results.append(_politics_crosschecked())
    except Exception:
        fail("뉴스-정치")
        results.append(["🏛️ 정치", "(연합뉴스·한경 접속 실패)", "잠시 후 다시 시도해주세요", None, ""])

    try:
        results.append(_single_category("🏙️ 사회", YONHAP_SOCIETY, "(요약 없음 — 원문 참고)"))
    except Exception:
        fail("뉴스-사회")
        results.append(["🏙️ 사회", "(연합뉴스 접속 실패)", "잠시 후 다시 시도해주세요", None, ""])

    try:
        results.append(_single_category("🌏 국제", YONHAP_INTERNATIONAL, "(요약 없음 — 원문 참고)"))
    except Exception:
        fail("뉴스-국제")
        results.append(["🌏 국제", "(연합뉴스 접속 실패)", "잠시 후 다시 시도해주세요", None, ""])

    try:
        # 한경 IT 피드는 <description>이 없어 제목만 온다.
        results.append(_single_category("🔬 과기", HANKYUNG_IT, "(요약 없음 — 원문 참고)"))
    except Exception:
        fail("뉴스-과기")
        results.append(["🔬 과기", "(한경 접속 실패)", "잠시 후 다시 시도해주세요", None, ""])

    try:
        results.append(_single_category("🎬 문화", YONHAP_CULTURE, "(요약 없음 — 원문 참고)"))
    except Exception:
        fail("뉴스-문화")
        results.append(["🎬 문화", "(연합뉴스 접속 실패)", "잠시 후 다시 시도해주세요", None, ""])

    ok_indices = [i for i, r in enumerate(results) if r[3]]  # link 있으면 = 조회 성공
    if ok_indices:
        try:
            items_for_llm = [{"label": results[i][0], "title": results[i][1], "lead": results[i][2]} for i in ok_indices]
            explanations = _llm.explain_news(items_for_llm)
            for idx, exp in zip(ok_indices, explanations):
                results[idx][2] = exp  # detail만 덮어씀 — source_note(4번째)는 그대로
        except Exception as e:
            print(f"[경고] 뉴스 배경설명(LLM) 실패: {type(e).__name__}: {e}")
            fail("뉴스 배경설명(LLM)")

    return [tuple(r) for r in results]
