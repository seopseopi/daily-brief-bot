"""Market section backed by Naver Finance and Yahoo Finance.

Display strings remain compatible with ``main.py`` while quote dictionaries
retain source timestamps/status. No value is called live unless its provider
reports an open regular market.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import settings
from sources import _market
from sources._shared import KST, fail

# Private holdings are configured only through environment-backed settings.
# Tuples keep accidental mutation out of a long-running process.
HOLDINGS_KR = tuple(settings.MARKET_HOLDINGS_KR)
HOLDINGS_US = tuple(settings.MARKET_HOLDINGS_US)


def _fmt_pct(value):
    if value is None:
        return "등락률 없음"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_arrow_pct(value):
    if value is None:
        return "등락률 없음"
    return f"{_market.arrow(value)}{abs(value):.2f}%"


def _iso_month_day_time(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%m/%d %H:%M")
    except (TypeError, ValueError):
        return ""


def _kr_basis(quote):
    status = str(quote.get("market_status") or "").upper()
    if status == "OPEN":
        label = "실시간"
    elif status == "PREOPEN":
        label = "전일 종가"
    elif status in {"CLOSE", "CLOSED"}:
        label = "종가"
    else:
        label = "기준가"
    as_of = _iso_month_day_time(quote.get("local_traded_at"))
    return f"{label} {as_of} KST".strip()


def _yahoo_time(quote):
    timestamp = quote.get("regular_market_time")
    if not isinstance(timestamp, (int, float)):
        return ""
    timezone_name = quote.get("exchange_timezone") or "UTC"
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = ZoneInfo("UTC")
    return datetime.fromtimestamp(timestamp, zone).strftime("%m/%d %H:%M 현지")


def _us_basis(quote):
    state = str(quote.get("market_state") or "").upper()
    if state in {"REGULAR", "OPEN"}:
        label = "정규장 실시간"
    elif state in {"PRE", "PREOPEN", "PREPRE"}:
        label = "개장 전 · 정규장 전일 종가"
    elif state in {"POST", "POSTPOST"}:
        label = "시간외 · 정규장 종가"
    else:
        label = "정규장 종가"
    as_of = _yahoo_time(quote)
    return f"{label} {as_of}".strip()


def _quote_metadata(quote, *, yahoo=False):
    if not quote:
        return {}
    if yahoo:
        return {
            "market_state": quote.get("market_state"),
            "market_state_source": quote.get("market_state_source"),
            "provider_market_state": quote.get("provider_market_state"),
            "regular_market_time": quote.get("regular_market_time"),
            "exchange_timezone": quote.get("exchange_timezone"),
            "source": quote.get("source"),
        }
    return {
        "market_status": quote.get("market_status"),
        "local_traded_at": quote.get("local_traded_at"),
        "market_session": quote.get("market_session"),
        "source": quote.get("source"),
    }


def _kr_index_and_note():
    quotes = _market.fetch_naver_quotes(["KOSPI", "KOSDAQ"])
    kospi, kosdaq = quotes.get("KOSPI"), quotes.get("KOSDAQ")

    if kospi and kospi.get("price") is not None:
        kr_index = (
            f"코스피 {kospi['price']:,.2f} {_fmt_arrow_pct(kospi.get('change_pct'))}"
            f" ({_kr_basis(kospi)})"
        )
    else:
        fail("코스피")
        kr_index = "(코스피 조회 실패)"

    note_parts = []
    if kosdaq and kosdaq.get("price") is not None:
        note_parts.append(
            f"코스닥 {kosdaq['price']:,.2f} {_fmt_arrow_pct(kosdaq.get('change_pct'))}"
            f" ({_kr_basis(kosdaq)})"
        )
    else:
        fail("코스닥")
        note_parts.append("(코스닥 조회 실패)")

    if kospi:
        if kospi.get("high") is not None:
            note_parts.append(f"코스피 고가 {kospi['high']:,.0f}")
        if kospi.get("low") is not None:
            note_parts.append(f"저가 {kospi['low']:,.0f}")

    metadata = {
        "KOSPI": _quote_metadata(kospi),
        "KOSDAQ": _quote_metadata(kosdaq),
    }
    return kr_index, " · ".join(note_parts), metadata


def _fetch_kr_quotes_partial(codes):
    """Retry a failed batch per symbol so one bad quote can still succeed."""
    if not codes:
        return {}
    try:
        return _market.fetch_naver_quotes(codes)
    except Exception as batch_error:
        recovered = {}
        for code in codes:
            try:
                recovered.update(_market.fetch_naver_quotes([code]))
            except Exception:
                continue
        if not recovered:
            raise batch_error
        return recovered


def _kr_holdings_and_hot():
    """Return holdings plus Naver's actual popular-search stocks."""
    try:
        hot_pairs = _market.fetch_naver_hot_search(limit=10)
    except Exception as exc:
        print(f"[경고] 네이버 인기검색 조회 실패: {type(exc).__name__}")
        fail("화제종목(국장)")
        hot_pairs = []

    holding_codes = set(HOLDINGS_KR)
    ranked_hot = [
        (rank, code, name)
        for rank, (code, name) in enumerate(hot_pairs, 1)
        if code not in holding_codes
    ][:2]
    requested_codes = list(HOLDINGS_KR) + [code for _, code, _ in ranked_hot]
    quotes = _fetch_kr_quotes_partial(requested_codes)

    holdings = []
    for code in HOLDINGS_KR:
        quote = quotes.get(code)
        if not quote or quote.get("price") is None:
            fail("보유종목(국장)")
            holdings.append((code, "(시세 조회 실패)", ""))
            continue
        display_name = quote.get("name") or code
        price = f"{quote['price']:,.0f} {_fmt_arrow_pct(quote.get('change_pct'))}"
        note = [_kr_basis(quote)]
        if quote.get("high") is not None:
            note.append(f"고가 {quote['high']:,.0f}")
        if quote.get("low") is not None:
            note.append(f"저가 {quote['low']:,.0f}")
        holdings.append((display_name, price, " · ".join(note)))

    hot = []
    for rank, code, source_name in ranked_hot:
        quote = quotes.get(code)
        if not quote or quote.get("price") is None:
            fail(f"화제종목(국장:{source_name})")
            continue
        price = f"{quote['price']:,.0f} {_fmt_arrow_pct(quote.get('change_pct'))}"
        hot.append((source_name, price, f"네이버 인기검색 {rank}위 · {_kr_basis(quote)}"))
    return holdings, hot


def _fetch_us_quote(symbol, failure_label):
    try:
        return _market.fetch_yahoo_quote(symbol)
    except Exception as exc:
        print(f"[경고] {failure_label} 조회 실패: {type(exc).__name__}")
        fail(failure_label)
        return None


def _us_index_and_note():
    sp = _fetch_us_quote("^GSPC", "S&P 500")
    nq = _fetch_us_quote("^IXIC", "나스닥")
    if not sp and not nq:
        raise RuntimeError("미국 주요 지수 둘 다 조회 실패")

    index_parts = []
    if nq:
        index_parts.append(f"나스닥 {_fmt_pct(nq.get('change_pct'))}")
    if sp:
        index_parts.append(f"S&P {_fmt_pct(sp.get('change_pct'))}")

    tnx = _fetch_us_quote("^TNX", "美 10년물")
    vix = _fetch_us_quote("^VIX", "VIX")
    note_parts = [_us_basis(nq or sp)]
    if tnx:
        note_parts.append(f"美10년물 {tnx['price']:.2f}%")
    if vix:
        note_parts.append(f"VIX {vix['price']:.1f}")
    if not tnx and not vix:
        note_parts.append("(금리·VIX 조회 실패)")

    metadata = {
        "S&P500": _quote_metadata(sp, yahoo=True),
        "NASDAQ": _quote_metadata(nq, yahoo=True),
    }
    return " · ".join(index_parts), " · ".join(note_parts), sp, nq, vix, metadata


def _us_holdings():
    out = []
    for symbol in HOLDINGS_US:
        quote = _fetch_us_quote(symbol, "보유종목(미장)")
        if not quote:
            out.append((symbol, "(조회 실패)", ""))
            continue
        display_name = quote.get("name") or symbol
        price = f"${quote['price']:,.2f} {_fmt_pct(quote.get('change_pct'))}"
        note = [_us_basis(quote)]
        if quote.get("day_high") is not None:
            note.append(f"정규장 고가 ${quote['day_high']:.2f}")
        if quote.get("day_low") is not None:
            note.append(f"저가 ${quote['day_low']:.2f}")
        out.append((display_name, price, " · ".join(note)))
    return out


def _us_hot():
    """Use Yahoo's live trending feed; omit honestly if it cannot be validated."""
    try:
        trending = _market.fetch_yahoo_trending("US", limit=10)
    except Exception as exc:
        print(f"[경고] Yahoo 트렌딩 조회 실패: {type(exc).__name__}")
        fail("화제종목(미장)")
        return []

    holdings = set(HOLDINGS_US)
    out = []
    for rank, symbol in enumerate(trending["symbols"], 1):
        if symbol in holdings:
            continue
        quote = _fetch_us_quote(symbol, f"화제종목(미장:{symbol})")
        if not quote:
            continue
        display_name = quote.get("name") or symbol
        price = f"${quote['price']:,.2f} {_fmt_pct(quote.get('change_pct'))}"
        out.append((display_name, price, f"Yahoo Finance 트렌딩 {rank}위 · {_us_basis(quote)}"))
        if len(out) >= 2:
            break
    if not out:
        fail("화제종목(미장)")
    return out


def _overnight_us_summary(sp, nq):
    """Describe the exact arithmetic used; this is not a Korean-market forecast."""
    available = [("S&P", sp), ("나스닥", nq)]
    available = [(name, quote) for name, quote in available if quote and quote.get("change_pct") is not None]
    details = " · ".join(f"{name} {_fmt_pct(quote['change_pct'])}" for name, quote in available)
    if len(available) != 2:
        return ("미국 주요지수 일부만 확인", details or "등락률 데이터를 가져오지 못했습니다")
    average = sum(quote["change_pct"] for _, quote in available) / len(available)
    return (
        f"간밤 미국 주요지수 단순평균 {_fmt_pct(average)}",
        f"{details}의 산술평균 · 국장 예측이나 투자 조언 아님",
    )


def _volatility_summary(vix):
    """Label the literal VIX threshold used rather than presenting an outlook."""
    if not vix:
        return ("VIX 조회 실패", "변동성 지표 데이터를 가져오지 못했습니다")
    value = vix["price"]
    if value < 15:
        interval, label = "VIX < 15", "낮음"
    elif value < 20:
        interval, label = "15 ≤ VIX < 20", "보통"
    else:
        interval, label = "VIX ≥ 20", "확대"
    return (f"VIX 구간: {label}", f"VIX {value:.1f} · 코드 기준 {interval} · 투자 조언 아님")


def _fx_line():
    rates = _market.fetch_naver_fx()
    labels = (("USD", "원/달러", 1), ("JPY100", "원/엔(100엔)", 1), ("CNY", "원/위안", 1))
    parts = []
    for key, label, _unit in labels:
        value = rates.get(key)
        if value is None:
            fail(f"환율({key})")
            continue
        parts.append(f"{label} {value:,.2f}")
    if not parts:
        raise RuntimeError("필수 환율이 모두 없음")
    return " · ".join(parts)


def get_market():
    """Build the legacy display contract plus structured source metadata."""
    fetched_at = datetime.now(KST).isoformat()
    try:
        kr_index, kr_note, kr_metadata = _kr_index_and_note()
    except Exception as exc:
        print(f"[경고] 코스피/코스닥 조회 실패: {type(exc).__name__}")
        fail("코스피/코스닥")
        kr_index, kr_note, kr_metadata = "(코스피 조회 실패)", "(코스닥 조회 실패)", {}

    try:
        kr_holdings, kr_hot = _kr_holdings_and_hot()
    except Exception as exc:
        print(f"[경고] 국장 종목 조회 실패: {type(exc).__name__}")
        fail("보유종목(국장)")
        kr_holdings, kr_hot = [], []

    try:
        us_index, us_note, sp, nq, vix, us_metadata = _us_index_and_note()
    except Exception as exc:
        print(f"[경고] 미국 지수 조회 실패: {type(exc).__name__}")
        fail("미국 지수")
        us_index, us_note = "(미국 지수 조회 실패)", "잠시 후 다시 시도해주세요"
        sp = nq = vix = None
        us_metadata = {}

    try:
        fx_string = _fx_line()
    except Exception as exc:
        print(f"[경고] 환율 조회 실패: {type(exc).__name__}")
        fail("환율")
        fx_string = "(환율 조회 실패)"

    return {
        "kr_index": kr_index,
        "kr_note": kr_note,
        "kr_holdings": kr_holdings,
        "kr_hot": kr_hot,
        "us_index": us_index,
        "us_note": us_note,
        "us_holdings": _us_holdings(),
        "us_hot": _us_hot(),
        "fx": fx_string,
        # Legacy keys kept for main.py; the values now state their exact formula.
        "outlook_kr": _overnight_us_summary(sp, nq),
        "outlook_us": _volatility_summary(vix),
        "market_metadata": {"kr_indices": kr_metadata, "us_indices": us_metadata},
        "as_of": fetched_at,
        "source_note": "네이버페이 증권 · Yahoo Finance · 각 항목 거래상태·기준시각 표기",
    }
