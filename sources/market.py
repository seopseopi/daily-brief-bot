"""마켓 섹션 — 네이버금융(국장) + 야후파이낸스(미장)."""

from sources import _market
from sources._shared import fail

HOLDINGS_KR = [("017670", "SK텔레콤"), ("009150", "삼성전기")]
HOLDINGS_US = [("SPCX", "SpaceX")]  # 2026년 상장 (NASDAQ) — 비상장 시절 하드코딩 문구는 폐기
WATCH_US = [("NVDA", "NVIDIA"), ("TSLA", "Tesla")]


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
        fail("美 금리·VIX")
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
            fail(f"미국 관심종목({name})")
            out.append((name, "(조회 실패)", ""))
    return out


def _us_holdings():
    out = []
    for symbol, name in HOLDINGS_US:
        try:
            q = _market.fetch_yahoo_quote(symbol)
            price_str = f"${q['price']:,.2f} {_fmt_pct(q['change_pct'])}"
            note = ""
            if q["day_high"] and q["day_low"]:
                note = f"일중 고가 ${q['day_high']:.2f} · 저가 ${q['day_low']:.2f}"
            out.append((name, price_str, note))
        except Exception:
            fail(f"보유종목(미장:{name})")
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
        fail("코스피/코스닥")
        kr_index, kr_note = "(코스피 조회 실패)", "잠시 후 다시 시도해주세요"

    try:
        kr_holdings, kr_hot = _kr_holdings_and_hot()
    except Exception:
        fail("보유·화제종목(국장)")
        kr_holdings, kr_hot = [], []

    try:
        us_index, us_note, sp, nq, vix_price = _us_index_and_note()
        outlook_kr = _kr_outlook(sp, nq)
    except Exception:
        fail("미국 지수")
        us_index, us_note = "(미국 지수 조회 실패)", "잠시 후 다시 시도해주세요"
        outlook_kr = ("(조회 실패)", "미국 지수 데이터를 가져오지 못했습니다")
        vix_price = None

    try:
        fx = _market.fetch_naver_fx()
        fx_str = f"원/달러 {fx['USD']:,.2f} · 원/엔(100엔) {fx['JPY100']:,.2f} · 원/위안 {fx['CNY']:,.2f}"
    except Exception:
        fail("환율")
        fx_str = "(환율 조회 실패)"

    return {
        "kr_index": kr_index,
        "kr_note": kr_note,
        "kr_holdings": kr_holdings,
        "kr_hot": kr_hot,
        "us_index": us_index,
        "us_note": us_note,
        "us_holdings": _us_holdings(),
        "us_hot": _us_hot(),
        "fx": fx_str,
        "outlook_kr": outlook_kr,
        "outlook_us": _us_outlook(vix_price),
    }
