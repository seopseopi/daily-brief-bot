"""각 섹션의 데이터 소스.

get_schedule() / get_assignments() / get_news()는 실제 데이터로 교체됨.
나머지는 아직 더미 데이터. 실제 API/크롤링으로 교체할 때 이 파일의
함수 하나씩만 갈아끼우면 된다.
"""

from datetime import date, datetime, timedelta, timezone

from sources import _rss
from sources.assignments_data import ASSIGNMENTS
from sources.timetable_fixed import DAY_END, DAY_START, FIXED_TIMETABLE

KST = timezone(timedelta(hours=9))

YONHAP_POLITICS = "https://www.yna.co.kr/rss/politics.xml"
YONHAP_SOCIETY = "https://www.yna.co.kr/rss/society.xml"
YONHAP_INTERNATIONAL = "https://www.yna.co.kr/rss/international.xml"
YONHAP_CULTURE = "https://www.yna.co.kr/rss/culture.xml"
HANKYUNG_POLITICS = "https://www.hankyung.com/feed/politics"
HANKYUNG_IT = "https://www.hankyung.com/feed/it"  # 연합뉴스엔 IT/과학 전용 피드가 없음

CROSSCHECK_THRESHOLD = 0.34  # 제목 토큰 겹침 비율 — 이 이상이면 "동시 보도"로 간주
DETAIL_MAX_LEN = 140


def _single_category(label, feed_url, fallback_note):
    """한 매체·한 카테고리에서 최신 1건을 뽑는다. 실패 시 예외를 던진다.

    반환: (라벨, 제목, 배경설명, 원문링크) — 링크는 본문에 노출하지 않고
    main.py가 "더보기" 버튼처럼 짧게 붙인다.
    """
    items = _rss.fetch_rss(feed_url)
    if not items:
        raise RuntimeError("empty feed")
    top = items[0]
    detail = _rss.clean_text(top["description"], DETAIL_MAX_LEN) or fallback_note
    return (label, top["title"], detail, top["link"])


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
            detail = f"{detail} (연합뉴스·한경 동시 보도)"
            return ("🏛️ 정치", best["title"], detail, best["link"])

    top = yh_items[0] if yh_items else hk_items[0]
    detail = _rss.clean_text(top["description"], DETAIL_MAX_LEN) or "단일 매체 확인"
    detail = f"{detail} (단일 매체 확인)"
    return ("🏛️ 정치", top["title"], detail, top["link"])


def get_highlights():
    """오늘의 세 줄. 다른 섹션 결과를 받아 LLM이 요약하는 게 최종 목표."""
    return [
        ("밤 9시 반 美 CPI", "예상 +2.6%. 웃돌면 금리 인하 기대 후퇴 → 반도체·성장주 조정 가능"),
        ("컴퓨터비전 과제 내일 마감", "오전 10:30~13:30 3시간 비어 있음"),
        ("9시 UROP 미팅", "프론트 API 연동 진척 공유 예정"),
    ]


def _to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def get_schedule():
    """고정 시간표(sources/timetable_fixed.py)에서 오늘 요일 것만 뽑는다.

    구글 캘린더 대신 매주 반복되는 수업·알바 시간을 하드코딩해 쓴다.
    시간이 바뀌면 timetable_fixed.py만 고치면 된다.
    """
    weekday = datetime.now(KST).weekday()  # 0=월 ... 6=일
    today = FIXED_TIMETABLE.get(weekday, [])

    events = [(f"{s}–{e}", name, detail) for s, e, name, detail in today]

    slots = []
    cursor = _to_minutes(DAY_START)
    day_end = _to_minutes(DAY_END)
    for s, e, _name, _detail in today:
        s_m, e_m = _to_minutes(s), _to_minutes(e)
        if s_m > cursor and s_m - cursor >= 30:
            hours = (s_m - cursor) / 60
            slots.append(f"{_to_hhmm(cursor)}~{_to_hhmm(s_m)} ({hours:g}h)")
        cursor = max(cursor, e_m)
    if day_end > cursor and day_end - cursor >= 30:
        hours = (day_end - cursor) / 60
        slots.append(f"{_to_hhmm(cursor)}~{_to_hhmm(day_end)} ({hours:g}h)")

    if slots:
        free_slots = " · ".join(slots)
    elif today:
        free_slots = "빈 시간 없음"
    else:
        free_slots = "오늘은 고정 일정 없음"

    return {"events": events, "free_slots": free_slots}


def get_assignments():
    """sources/assignments_data.py에 수동으로 적어둔 과제 목록을 D-day로 변환.

    새 과제가 생기면 그 파일에 한 줄 추가하면 된다. 마감이 지난 항목은
    자동으로 제외되니 지울 필요 없음.
    """
    today = datetime.now(KST).date()
    result = []
    for deadline_str, name, note in ASSIGNMENTS:
        y, m, d = (int(x) for x in deadline_str.split("-"))
        days = (date(y, m, d) - today).days
        if days < 0:
            continue
        result.append((days, name, note))
    result.sort(key=lambda x: x[0])
    return result


def get_market():
    """TODO: 네이버금융/야후파이낸스 크롤링"""
    return {
        "kr_index": "코스피 2,742 ▲0.4%",
        "kr_note": "외인 +3,200억 순매수 · 기관 -1,100억 · 반도체가 지수 견인",
        "kr_holdings": [
            ("SK텔레콤", "58,400 ▲1.2%", "AI 데이터센터 투자 확대 발표. 통신 3사 중 AI 매출 비중이 가장 빠르게 증가"),
            ("삼성전기", "152,000 ▲2.8%", "MLCC 수요 회복 신호. AI 서버·전장용 고부가 비중 확대가 실적 레버리지"),
        ],
        "kr_hot": [
            ("삼성전자", "▲5.1%", "외인 3거래일만 순매수 전환. HBM4 공급 계약 기대감이 촉매"),
            ("에코프로", "▼3.6%", "증권가 목표주가 하향. 中 저가 배터리 공세로 마진 압박"),
        ],
        "us_index": "나스닥 ▲0.9% · S&P ▲0.6%",
        "us_note": "美10년물 4.12% · VIX 14.2 (변동성 낮음)",
        "us_holdings": [
            ("SpaceX", "비상장", "최근 라운드 밸류 상향 보도. 스타링크 매출 성장이 밸류 근거로 거론"),
        ],
        "us_hot": [
            ("NVIDIA", "▲2.1%", "모레 실적 발표. 데이터센터 가이던스가 반도체 섹터 방향 좌우"),
            ("Tesla", "▼1.8%", "분기 인도량 컨센서스 하회 우려"),
        ],
        "fx": "원/달러 1,338 · 원/엔 905 · 원/위안 186",
        "outlook_kr": ("상승 우위", "간밤 미국 반도체 강세 + 외인 순매수 지속. 다만 밤 CPI 대기로 관망세, 상단 제한적"),
        "outlook_us": ("혼조", "엔비디아 실적 기대 vs 금리 부담. CPI 결과 전까지 방향성 나오기 어려움"),
    }


def get_news():
    """연합뉴스/한경 RSS 최신 1건씩. 정치는 두 매체 교차확인.

    각 카테고리는 독립적으로 fallback 처리한다 — 하나가 실패해도
    나머지 카테고리는 정상 출력되고, 브리핑 전체는 깨지지 않는다.
    """
    try:
        politics = _politics_crosschecked()
    except Exception:
        politics = ("🏛️ 정치", "(연합뉴스·한경 접속 실패)", "잠시 후 다시 시도해주세요", None)

    try:
        society = _single_category("🏙️ 사회", YONHAP_SOCIETY, "(요약 없음 — 원문 참고)")
    except Exception:
        society = ("🏙️ 사회", "(연합뉴스 접속 실패)", "잠시 후 다시 시도해주세요", None)

    try:
        international = _single_category("🌏 국제", YONHAP_INTERNATIONAL, "(요약 없음 — 원문 참고)")
    except Exception:
        international = ("🌏 국제", "(연합뉴스 접속 실패)", "잠시 후 다시 시도해주세요", None)

    try:
        # 한경 IT 피드는 <description>이 없어 제목만 온다.
        tech = _single_category("🔬 과기", HANKYUNG_IT, "(요약 없음 — 원문 참고)")
    except Exception:
        tech = ("🔬 과기", "(한경 접속 실패)", "잠시 후 다시 시도해주세요", None)

    try:
        culture = _single_category("🎬 문화", YONHAP_CULTURE, "(요약 없음 — 원문 참고)")
    except Exception:
        culture = ("🎬 문화", "(연합뉴스 접속 실패)", "잠시 후 다시 시도해주세요", None)

    return [politics, society, international, tech, culture]


def get_sports():
    """TODO: KBO/EPL 스코어 API"""
    return {
        "doosan": ("두산 4-6 LG 패", "김재환 2안타 1타점, 선발 5이닝 3실점. 불펜 8회 역전 허용",
                   "5위 (63승 2무 61패) · 5강 -1.5G · 오늘 18:30 vs KT 잠실"),
        "football": "EPL 토트넘 2-1 승 (손흥민 도움 1) · 레알 3-0 완승",
    }


def get_study():
    """TODO: arXiv API + HF Daily Papers + LLM 요약"""
    return {
        "paper_title": "VLM은 자기가 틀렸다는 걸 아는가",
        "paper_meta": "arXiv · cs.CV",
        "paper_url": "https://arxiv.org/",
        "paper_sections": [
            ("문제의식", "VLM이 오답을 낼 때 confidence도 함께 낮아지는가. 모델이 자기 실패를 인지하는가를 정량 측정"),
            ("방법", "5개 VQA 벤치마크에서 난이도 구간별 ECE 측정, hallucination 구간 분리 분석"),
            ("결과", "난이도↑ 시 정확도만 급락하고 confidence는 유지 → 과확신 심화. uncertainty 헤드로 ECE 30% 개선"),
            ("한계", "멀티모달 특유 요인과 텍스트 공통 요인이 분리되지 않음"),
            ("네 연구와의 접점", "visual state tracking 실패 구간에도 동일한 측정틀 적용 가능"),
        ],
        "concept": ("ECE", "예측 confidence를 구간으로 나눠 평균 확신도와 실제 정확도 차이를 가중평균. 0에 가까울수록 잘 보정됨. Adaptive ECE, Brier score 병기가 관행"),
        "terms": [
            ("ablation study", "구성요소를 하나씩 빼며 기여도를 검증하는 실험. 논문 후반부에 거의 필수"),
            ("inductive bias", "모델 구조에 내재된 가정. CNN의 지역성, Transformer의 순서 무관성이 대표 예"),
            ("orthogonal to", "\"~와는 별개 축의 문제다\". 논점 분리할 때 자주 씀"),
        ],
    }


def get_community():
    """TODO: 디시 스크래핑 + Reddit API"""
    return [
        ("특이점이 온다 갤", "조회 5.8만 · 댓글 420", "데이터센터 속 AI들의 문명 논문 공유글",
         "arXiv 원문과 함께 다중 에이전트 환경의 창발적 협력 패턴 논문 요약. 댓글에서 실험 설계 타당성 논쟁"),
        ("클로드 갤", "조회 4.2만 · 댓글 380", "신모델 코딩 테스트 해봄 - 반응 갈림",
         "리팩터링은 호평, 엣지케이스는 지적. 공식 벤치마크와 체감 편차 논쟁 — 벤치마크 신뢰성 이슈와 직결"),
        ("챗지피티 갤", "조회 2.9만 · 댓글 210", "이미지 인식 오류 사례 모음",
         "표·손글씨에서 반복 오탐 축적. 실사용 hallucination 아카이브로 참고 가치"),
        ("AI 활용 갤", "조회 1.7만 · 댓글 150", "에이전트 스택 구성 실전 후기",
         "툴 체이닝 실패 지점 공유. 실무 관점 uncertainty 처리 사례"),
        ("r/LocalLLaMA", "업보트 1.8k · 댓글 240", "New open-weight VLM claims SOTA on hallucination",
         "저자 주장 수치 재현이 어렵다는 댓글 다수. 재현성 논쟁 진행중"),
    ]
