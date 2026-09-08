"""각 섹션의 데이터 소스.

get_schedule() / get_assignments() / get_news()는 실제 데이터로 교체됨.
나머지는 아직 더미 데이터. 실제 API/크롤링으로 교체할 때 이 파일의
함수 하나씩만 갈아끼우면 된다.
"""

from datetime import date, datetime, timedelta, timezone

from sources import _arxiv, _community, _llm, _market, _rss, _translate
from sources.assignments_data import ASSIGNMENTS
from sources.timetable_fixed import DAY_END, DAY_START, FIXED_TIMETABLE

KST = timezone(timedelta(hours=9))

HOLDINGS_KR = [("017670", "SK텔레콤"), ("009150", "삼성전기")]
WATCH_US = [("NVDA", "NVIDIA"), ("TSLA", "Tesla")]

DOOSAN_CODE = "OB"
NAVER_SPORTS_GAMES = "https://api-gw.sports.naver.com/schedule/games"
EPL_BIG_CLUBS = {"맨시티", "아스널", "리버풀", "첼시", "맨유", "토트넘"}

DC_GALLERIES = [
    ("thesingularity", "특이점이 온다 갤"),
    ("claude", "클로드 갤"),
    ("chatgpt", "챗지피티 갤"),
    ("chatgptpro", "GPT프로 갤"),
    ("aiinformation", "AI 정보 갤"),
]
REDDIT_SUBS = [("LocalLLaMA", "r/LocalLLaMA"), ("ClaudeAI", "r/ClaudeAI")]
NO_EXCERPT_NOTE = "(본문 요약 없음 — 더보기 참고)"

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

# "오늘의 개념" 후보 — 날짜로 하나씩 순환 (매일 같은 값 아님, 랜덤도 아님)
GLOSSARY_CONCEPTS = [
    ("ECE (Expected Calibration Error)", "예측 confidence를 구간으로 나눠 평균 확신도와 실제 정확도 차이를 가중평균한 값. 0에 가까울수록 잘 보정됨. Adaptive ECE, Brier score를 같이 언급하는 경우가 많음"),
    ("Epistemic vs Aleatoric Uncertainty", "Epistemic은 모델이 몰라서 생기는 불확실성(데이터·학습으로 줄일 수 있음), Aleatoric은 데이터 자체의 노이즈로 생기는 불확실성(늘려도 안 줄어듦). 두 종류를 구분해야 불확실성 추정이 의미 있어짐"),
    ("In-context Learning", "파라미터 업데이트 없이, 프롬프트에 넣은 예시만으로 모델이 새 태스크를 수행하는 능력. LLM 스케일이 커지면서 두드러지게 나타난 현상"),
    ("RLHF (Reinforcement Learning from Human Feedback)", "사람이 매긴 선호도로 보상모델을 학습시키고, 그 보상모델로 LLM을 강화학습시키는 정렬(alignment) 기법. ChatGPT류 모델 후처리의 핵심 단계"),
    ("Contrastive Learning", "같은 대상의 서로 다른 표현(augmentation)은 가깝게, 다른 대상은 멀게 임베딩 공간을 학습시키는 방법. CLIP 같은 비전-언어 정렬 모델의 기반"),
    ("Chain-of-Thought Prompting", "정답만 바로 내지 말고 중간 추론 과정을 순서대로 생성하게 유도하는 프롬프트 기법. 복잡한 추론 태스크에서 정확도를 크게 끌어올림"),
    ("Grounding (멀티모달)", "언어로 지칭한 대상을 이미지·비디오의 실제 픽셀/영역/시점에 정확히 대응시키는 능력. 이게 약하면 모델이 '말은 하는데 실제로 못 보는' 상태가 됨"),
    ("Catastrophic Forgetting", "새 태스크를 학습하면서 이전에 배운 지식을 급격히 잊어버리는 현상. 연속학습(continual learning) 연구의 핵심 문제"),
    ("Distribution Shift", "학습 데이터와 실제 배포 환경의 데이터 분포가 달라지는 상황. 모델 성능 저하와 신뢰도 오보정(calibration 붕괴)의 주요 원인"),
    ("Self-Consistency", "같은 질문에 여러 번 샘플링해 답을 낸 뒤 다수결로 최종 답을 정하는 디코딩 전략. Chain-of-Thought와 묶어 쓰면 정확도가 오름"),
]

# "오늘의 빈출 용어" 후보 — 3개씩 순환
GLOSSARY_TERMS = [
    ("ablation study", "구성요소를 하나씩 빼며 기여도를 검증하는 실험. 논문 후반부에 거의 필수"),
    ("inductive bias", "모델 구조에 내재된 가정. CNN의 지역성, Transformer의 순서 무관성이 대표 예"),
    ("orthogonal to", '"~와는 별개 축의 문제다". 논점 분리할 때 자주 씀'),
    ("zero-shot / few-shot", "학습 예시를 아예 안 주거나(zero-shot) 몇 개만 주고(few-shot) 바로 평가하는 세팅"),
    ("fine-tuning", "사전학습된 모델을 특정 태스크·도메인 데이터로 추가 학습시키는 것"),
    ("embedding", "텍스트·이미지 등을 고정 차원의 실수 벡터로 바꾼 표현. 벡터 간 거리가 의미적 유사도를 반영하도록 학습됨"),
    ("perplexity", "언어모델이 다음 토큰을 얼마나 잘 예측하는지 나타내는 지표. 낮을수록 모델이 데이터를 잘 설명한다는 뜻"),
    ("attention mechanism", "입력의 각 부분에 서로 다른 가중치를 줘서, 지금 필요한 정보에 더 집중하게 하는 메커니즘. Transformer의 핵심"),
    ("benchmark", "여러 모델·방법을 같은 기준으로 비교하기 위한 표준화된 데이터셋+평가 프로토콜"),
]

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


def get_highlights(context_text=""):
    """다른 6개 섹션의 실제 내용을 받아 LLM(Claude Haiku)이 세 줄로 요약.

    ANTHROPIC_API_KEY가 없거나 호출이 실패하면 조용히 비-LLM 폴백으로
    내려간다 — 브리핑 자체는 항상 나가야 하므로.
    """
    import urllib.error

    try:
        return _llm.summarize_highlights(context_text)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[경고] LLM 요약 실패: HTTP {e.code}\n{body}")
        return [("오늘의 세 줄 요약 실패", "아래 섹션을 직접 확인해주세요 — LLM 호출이 안 됐습니다")]
    except Exception as e:
        print(f"[경고] LLM 요약 실패: {type(e).__name__}: {e}")
        return [("오늘의 세 줄 요약 실패", "아래 섹션을 직접 확인해주세요 — LLM 호출이 안 됐습니다")]


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


def _fmt_pct(x):
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.2f}%"


def _kr_index_and_note():
    idx = _market.fetch_naver_quotes(["KOSPI", "KOSDAQ"])
    kospi, kosdaq = idx["KOSPI"], idx["KOSDAQ"]
    kr_index = f"코스피 {kospi['price']:,.2f} {_market.arrow(kospi['change_pct'])}{abs(kospi['change_pct']):.2f}%"
    kr_note = (
        f"코스닥 {kosdaq['price']:,.2f} {_market.arrow(kosdaq['change_pct'])}{abs(kosdaq['change_pct']):.2f}% · "
        f"코스피 고가 {kospi['high']:,.0f} · 저가 {kospi['low']:,.0f}"
    )
    return kr_index, kr_note


def _kr_holdings_and_hot():
    """보유 종목 + 화제종목(네이버 인기검색 순위 기준, 보유 종목은 제외)."""
    hot_pairs = _market.fetch_naver_hot_search(limit=10)
    holding_codes = {c for c, _ in HOLDINGS_KR}
    hot_codes = [c for c, _ in hot_pairs if c not in holding_codes][:2]
    quotes = _market.fetch_naver_quotes([c for c, _ in HOLDINGS_KR] + hot_codes)

    kr_holdings = []
    for code, name in HOLDINGS_KR:
        q = quotes.get(code)
        if not q:
            continue
        price_str = f"{q['price']:,.0f} {_market.arrow(q['change_pct'])}{abs(q['change_pct']):.2f}%"
        note = f"고가 {q['high']:,.0f} · 저가 {q['low']:,.0f}"
        kr_holdings.append((name, price_str, note))

    hot_name_lookup = dict(hot_pairs)
    kr_hot = []
    for rank, code in enumerate(hot_codes, 1):
        q = quotes.get(code)
        if not q:
            continue
        change_str = f"{_market.arrow(q['change_pct'])}{abs(q['change_pct']):.2f}%"
        kr_hot.append((hot_name_lookup.get(code, q["name"]), change_str, f"네이버 인기검색 {rank}위"))

    return kr_holdings, kr_hot


def _us_index_and_note():
    sp = _market.fetch_yahoo_quote("^GSPC")
    nq = _market.fetch_yahoo_quote("^IXIC")
    us_index = f"나스닥 {_fmt_pct(nq['change_pct'])} · S&P {_fmt_pct(sp['change_pct'])}"
    try:
        tnx = _market.fetch_yahoo_quote("^TNX")
        vix = _market.fetch_yahoo_quote("^VIX")
        us_note = f"美10년물 {tnx['price']:.2f}% · VIX {vix['price']:.1f}"
        vix_price = vix["price"]
    except Exception:
        us_note = "(금리·VIX 조회 실패)"
        vix_price = None
    return us_index, us_note, sp, nq, vix_price


def _us_hot():
    out = []
    for symbol, name in WATCH_US:
        try:
            q = _market.fetch_yahoo_quote(symbol)
            note = ""
            if q["day_high"] and q["day_low"]:
                note = f"일중 고가 ${q['day_high']:.2f} · 저가 ${q['day_low']:.2f}"
            out.append((name, _fmt_pct(q["change_pct"]), note))
        except Exception:
            out.append((name, "(조회 실패)", ""))
    return out


def _kr_outlook(sp, nq):
    """국장 개장 전 참고용 — 간밤 미국 지수 흐름을 그대로 요약. 예측/추천 아님."""
    avg = (sp["change_pct"] + nq["change_pct"]) / 2
    if avg > 0.3:
        label = "미국 증시 상승 마감"
    elif avg < -0.3:
        label = "미국 증시 하락 마감"
    else:
        label = "미국 증시 혼조 마감"
    detail = (
        f"S&P {_fmt_pct(sp['change_pct'])} · 나스닥 {_fmt_pct(nq['change_pct'])}. "
        "국장 방향성 참고용 — 투자 조언 아님"
    )
    return (label, detail)


def _us_outlook(vix_price):
    """VIX 기준 변동성 읽기 — 매수/매도 신호 아님, 참고용 지표 설명."""
    if vix_price is None:
        return ("(조회 실패)", "VIX 데이터를 가져오지 못했습니다")
    if vix_price < 15:
        label = "변동성 낮음"
    elif vix_price < 20:
        label = "변동성 보통"
    else:
        label = "변동성 확대"
    return (label, f"VIX {vix_price:.1f} 기준. 심리 지표 참고용 — 투자 조언 아님")


def get_market():
    """네이버금융(국장) + 야후파이낸스(미장). 각 구획은 독립 fallback 처리."""
    try:
        kr_index, kr_note = _kr_index_and_note()
    except Exception:
        kr_index, kr_note = "(코스피 조회 실패)", "잠시 후 다시 시도해주세요"

    try:
        kr_holdings, kr_hot = _kr_holdings_and_hot()
    except Exception:
        kr_holdings, kr_hot = [], []

    try:
        us_index, us_note, sp, nq, vix_price = _us_index_and_note()
        outlook_kr = _kr_outlook(sp, nq)
    except Exception:
        us_index, us_note = "(미국 지수 조회 실패)", "잠시 후 다시 시도해주세요"
        outlook_kr = ("(조회 실패)", "미국 지수 데이터를 가져오지 못했습니다")
        vix_price = None

    try:
        fx = _market.fetch_naver_fx()
        fx_str = f"원/달러 {fx['USD']:,.2f} · 원/엔(100엔) {fx['JPY100']:,.2f} · 원/위안 {fx['CNY']:,.2f}"
    except Exception:
        fx_str = "(환율 조회 실패)"

    return {
        "kr_index": kr_index,
        "kr_note": kr_note,
        "kr_holdings": kr_holdings,
        "kr_hot": kr_hot,
        "us_index": us_index,
        "us_note": us_note,
        "us_holdings": [("SpaceX", "비상장", "실시간 시세 데이터 없음 (비상장사)")],
        "us_hot": _us_hot(),
        "fx": fx_str,
        "outlook_kr": outlook_kr,
        "outlook_us": _us_outlook(vix_price),
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


def _doosan_line(game):
    is_home = game["homeTeamCode"] == DOOSAN_CODE
    mine = game["homeTeamScore"] if is_home else game["awayTeamScore"]
    theirs = game["awayTeamScore"] if is_home else game["homeTeamScore"]
    opp = game["awayTeamName"] if is_home else game["homeTeamName"]
    outcome = "승" if mine > theirs else "패" if mine < theirs else "무"
    return f"두산 {mine}-{theirs} {opp} ({outcome})"


def _kbo():
    """두산 최근 경기 결과 + 다음 경기 일정.

    네이버스포츠 비공식 API. 시즌 순위/게임차를 주는 무료 엔드포인트를
    찾지 못해 그 부분은 뺐다 — 필요하면 나중에 추가.
    """
    today = datetime.now(KST).date()
    url = (
        f"{NAVER_SPORTS_GAMES}?fields=basic,score&size=50"
        f"&fromDate={today - timedelta(days=4)}&toDate={today + timedelta(days=1)}"
        "&upperCategoryId=kbaseball&categoryId=kbo"
    )
    games = _market.fetch_json(url)["result"]["games"]
    doosan_games = [g for g in games if DOOSAN_CODE in (g["homeTeamCode"], g["awayTeamCode"])]

    results = sorted((g for g in doosan_games if g["statusCode"] == "RESULT"),
                      key=lambda g: g["gameDate"], reverse=True)
    upcoming = sorted((g for g in doosan_games if g["statusCode"] == "BEFORE"),
                       key=lambda g: g["gameDateTime"])

    if results:
        head = _doosan_line(results[0])
        detail = f"{results[0]['gameDate']} 경기 종료"
    else:
        head, detail = "(최근 경기 결과 없음)", ""

    if upcoming:
        g = upcoming[0]
        is_home = g["homeTeamCode"] == DOOSAN_CODE
        opp = g["awayTeamName"] if is_home else g["homeTeamName"]
        when = datetime.fromisoformat(g["gameDateTime"]).strftime("%m/%d %H:%M")
        next_game = f"다음 경기 {when} vs {opp} ({'홈' if is_home else '원정'})"
    else:
        next_game = "(예정된 경기 없음)"

    return (head, detail, next_game)


def _epl_highlights(limit=2):
    """빅클럽(맨시티·아스널·리버풀·첼시·맨유·토트넘)이 낀 최근 경기 결과만 추린다."""
    today = datetime.now(KST).date()
    url = (
        f"{NAVER_SPORTS_GAMES}?fields=basic,score&size=50"
        f"&fromDate={today - timedelta(days=5)}&toDate={today}"
        "&upperCategoryId=wfootball&categoryId=epl"
    )
    games = _market.fetch_json(url)["result"]["games"]

    scored = []
    for g in games:
        if g["statusCode"] != "RESULT":
            continue
        big_count = (g["homeTeamName"] in EPL_BIG_CLUBS) + (g["awayTeamName"] in EPL_BIG_CLUBS)
        if big_count:
            scored.append((g["gameDate"], big_count, g))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    lines = [
        f"{g['homeTeamName']} {g['homeTeamScore']}-{g['awayTeamScore']} {g['awayTeamName']}"
        for _, _, g in scored[:limit]
    ]
    return " · ".join(lines) if lines else "(주요 경기 결과 없음)"


def get_sports():
    """KBO(두산) + EPL. 네이버스포츠 비공식 API, 각 종목 독립 fallback."""
    try:
        doosan = _kbo()
    except Exception:
        doosan = ("(두산 경기 조회 실패)", "잠시 후 다시 시도해주세요", "")

    try:
        football = _epl_highlights()
    except Exception:
        football = "(EPL 결과 조회 실패)"

    return {"doosan": doosan, "football": football}


def _tr(text, cap=180):
    """번역 실패해도 원문(영어)으로 폴백 — 섹션 하나 때문에 전체가 죽지 않게."""
    if not text:
        return ""
    try:
        return _translate.translate_en_ko(text, max_len=cap)
    except Exception:
        return text


def _pick_glossary_concept():
    idx = datetime.now(KST).date().toordinal() % len(GLOSSARY_CONCEPTS)
    return GLOSSARY_CONCEPTS[idx]


def _pick_glossary_terms(n=3):
    total = len(GLOSSARY_TERMS)
    offset = datetime.now(KST).date().toordinal() % total
    return [GLOSSARY_TERMS[(offset + i) % total] for i in range(n)]


def get_study():
    """arXiv에서 관심 키워드에 걸리는 최신 논문 1편을 골라 초록을 정리한다.

    LLM 요약이 아니라 초록을 문장 위치로 잘라 배치하는 근사치다
    (문제의식=첫 문장, 방법=중간, 결과=끝 문장 — 논문 초록의 흔한 서술
    순서를 이용). 한계는 "however/limitation" 류 신호어가 있는 문장을
    찾아 쓰고, 없으면 정직하게 "명시 없음"이라고 표시한다.
    "내 연구와의 접점"은 추론이 아니라 실제로 매칭된 키워드를 그대로 보여준다.
    개념/용어는 정적 용어집을 날짜로 순환한다 (LLM 호출 없음).
    """
    try:
        papers = _arxiv.search(RESEARCH_KEYWORDS, ARXIV_CATEGORIES, max_results=15)
        best, matched = _arxiv.pick_best(papers, RESEARCH_KEYWORDS)
    except Exception as e:
        print(f"[경고] arXiv 조회 실패: {type(e).__name__}: {e}")
        best, matched = None, []

    if best:
        problem, method, result, limitation = _arxiv.split_sections(best["summary"])
        sections = [("문제의식", _tr(problem))]
        if method:
            sections.append(("방법", _tr(method, cap=220)))
        if result:
            sections.append(("결과", _tr(result)))
        sections.append(("한계", _tr(limitation) if limitation else "초록에 명시된 한계 없음 — 원문 참고"))
        sections.append((
            "내 연구와의 접점",
            f"키워드 매칭: {', '.join(matched)}" if matched else "카테고리 기준으로만 선정됨 (키워드 매칭 없음)",
        ))

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

    return {
        "paper_title": paper_title,
        "paper_meta": paper_meta,
        "paper_url": paper_url,
        "paper_sections": sections,
        "concept": _pick_glossary_concept(),
        "terms": _pick_glossary_terms(),
    }


def get_community():
    """디시(5개 갤러리) + 레딧(2개 서브) 화제글. 조회수/댓글수 상위, 최소한의 혐오·자극 필터.

    목록 페이지에는 본문이 없어서(디시 리스트, 레딧 RSS 둘 다) "디깅 요약"은
    아직 못 넣는다 — 있는 그대로 "본문 요약 없음"이라 표시하고 더보기 링크로
    대신한다. 갤러리/서브레딧 하나가 막혀도 나머지는 정상 출력된다.
    """
    dc_hits = []
    for gallery_id, label in DC_GALLERIES:
        try:
            post = _community.fetch_dc_top_post(gallery_id)
        except Exception:
            post = None
        if post:
            dc_hits.append((label, post))
    dc_hits.sort(key=lambda x: -x[1]["views"])

    reddit_hits = []
    for sub_id, label in REDDIT_SUBS:
        try:
            post = _community.fetch_reddit_top_post(sub_id)
        except Exception:
            post = None
        if post:
            reddit_hits.append((label, post))

    entries = []
    for label, post in dc_hits[:3]:
        stat = f"조회 {post['views']:,} · 댓글 {post['replies']}"
        entries.append((label, stat, post["title"], NO_EXCERPT_NOTE, post["url"]))

    for label, post in reddit_hits:
        entries.append((label, "레딧 오늘의 인기글", _tr(post["title"], cap=100), NO_EXCERPT_NOTE, post["url"]))

    for label, post in dc_hits[3:]:
        if len(entries) >= 5:
            break
        stat = f"조회 {post['views']:,} · 댓글 {post['replies']}"
        entries.append((label, stat, post["title"], NO_EXCERPT_NOTE, post["url"]))

    if not entries:
        entries = [("(커뮤니티 조회 실패)", "", "잠시 후 다시 시도해주세요", "", None)]

    return entries
