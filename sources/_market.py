"""Market data transport/parsing helpers (standard library only).

The upstream endpoints used here are public but undocumented. Consequently
every parser is strict about response shape and lenient about nullable quote
fields. A missing intraday high/low (Naver returns ``"-"`` before opening)
must not discard an otherwise valid quote.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from http_client import open_url

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 8

NAVER_POPULAR_URL = (
    "https://stock.naver.com/api/domestic/market/stock/default"
    "?tradeType=KRX&marketType=ALL&orderType=searchTop&startIdx=0&pageSize={limit}"
)

YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
YAHOO_ATTEMPTS = 3
YAHOO_RETRY_BASE_SECONDS = 0.5
YAHOO_RETRY_MAX_SECONDS = 3.0


def _get(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html,*/*"},
    )
    with open_url(req, timeout=TIMEOUT) as res:
        return res.read()


def fetch_json(url):
    """JSON fetch shared with the sports adapter."""
    return json.loads(_get(url))


def _num(value):
    """Return a provider value as ``float``, or ``None`` when unavailable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).strip().replace(",", "")
    if not cleaned or cleaned.upper() in {"-", "--", "N/A", "NA", "NULL", "NONE"}:
        return None
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _first_number(mapping, *keys):
    for key in keys:
        number = _num(mapping.get(key))
        if number is not None:
            return number
    return None


def fetch_naver_quotes(codes):
    """Fetch Korean quotes without letting one missing field poison the batch.

    Naver's ``marketStatus`` and ``localTradedAt`` are retained alongside the
    legacy price keys so callers can distinguish live prices from prior closes.
    """
    if not codes:
        return {}
    is_index = all(str(code).isalpha() for code in codes)
    kind = "index" if is_index else "stock"
    encoded_codes = ",".join(urllib.parse.quote(str(code), safe="") for code in codes)
    url = f"https://polling.finance.naver.com/api/realtime/domestic/{kind}/{encoded_codes}"
    data = json.loads(_get(url))
    rows = data.get("datas") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Naver quote response has no datas list")

    out = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        code = str(item.get("itemCode") or item.get("symbolCode") or "").strip()
        if not code:
            continue
        out[code] = {
            "name": str(item.get("stockName") or code).strip(),
            "price": _first_number(item, "closePriceRaw", "closePrice"),
            "change_pct": _first_number(item, "fluctuationsRatioRaw", "fluctuationsRatio"),
            "change": _first_number(
                item, "compareToPreviousClosePriceRaw", "compareToPreviousClosePrice"
            ),
            "open": _first_number(item, "openPriceRaw", "openPrice"),
            "high": _first_number(item, "highPriceRaw", "highPrice"),
            "low": _first_number(item, "lowPriceRaw", "lowPrice"),
            "value": item.get("accumulatedTradingValueRaw")
            or item.get("accumulatedTradingValue")
            or "",
            "market_status": item.get("marketStatus"),
            "market_status_detail": item.get("marketStatusDetailType"),
            "market_session": item.get("marketSessionType"),
            "local_traded_at": item.get("localTradedAt"),
            "source": "Naver Finance realtime",
        }
    return out


def fetch_naver_hot_search(limit=10):
    """Return Naver Finance's current popular-search ranking.

    The former ``lastsearch2.naver`` page now redirects to a Next.js app. Its
    current JSON endpoint explicitly requests ``orderType=searchTop``. Empty or
    malformed responses are errors, allowing the caller to omit the section
    honestly instead of presenting a false empty ranking.
    """
    if limit <= 0:
        return []
    data = json.loads(_get(NAVER_POPULAR_URL.format(limit=int(limit))))
    if not isinstance(data, list):
        raise ValueError("Naver popular-stock response is not a list")

    pairs = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        code = str(item.get("itemcode") or "").strip()
        name = html.unescape(str(item.get("itemname") or "")).strip()
        if not re.fullmatch(r"\d{6}", code) or not name or code in seen:
            continue
        seen.add(code)
        pairs.append((code, name))
        if len(pairs) >= limit:
            break
    if not pairs:
        raise ValueError("Naver popular-stock response contained no valid stocks")
    return pairs


def fetch_naver_fx():
    """USD/JPY(100 yen)/CNY rates in KRW."""
    raw = _get("https://finance.naver.com/marketindex/exchangeList.naver")
    text = raw.decode("euc-kr", errors="replace")
    rows = re.findall(r"<tr[^>]*>.*?</tr>", text, re.S)
    result = {}
    label_map = {"미국": "USD", "일본": "JPY100", "중국": "CNY"}
    for row in rows:
        name_m = re.search(r'<td class="tit">.*?<a[^>]*>\s*([^<]+?)\s*</a>', row, re.S)
        sale_m = re.search(r'<td class="sale">([^<]+)</td>', row)
        if not (name_m and sale_m):
            continue
        name = html.unescape(name_m.group(1))
        for prefix, key in label_map.items():
            if name.startswith(prefix):
                rate = _num(sale_m.group(1))
                if rate is not None:
                    result[key] = rate
    return result


def _retry_delay(exc, attempt):
    retry_after = None
    if isinstance(exc, urllib.error.HTTPError) and exc.headers:
        retry_after = _num(exc.headers.get("Retry-After"))
    delay = retry_after if retry_after is not None else YAHOO_RETRY_BASE_SECONDS * (2**attempt)
    return max(0.0, min(delay, YAHOO_RETRY_MAX_SECONDS))


def _fetch_yahoo_json(path, validator):
    """Fetch Yahoo JSON with bounded retries and query1/query2 failover."""
    last_error = None
    for attempt in range(YAHOO_ATTEMPTS):
        host = YAHOO_HOSTS[attempt % len(YAHOO_HOSTS)]
        url = f"https://{host}{path}"
        try:
            data = json.loads(_get(url))
            if not validator(data):
                raise ValueError("Yahoo response failed schema validation")
            return data
        except urllib.error.HTTPError as exc:
            # Auth/not-found errors will not improve by switching mirrors.
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc

        if attempt < YAHOO_ATTEMPTS - 1:
            time.sleep(_retry_delay(last_error, attempt))

    if last_error is not None:
        raise last_error
    raise RuntimeError("Yahoo request failed")


def _valid_yahoo_chart(data):
    try:
        result = data["chart"]["result"]
        return isinstance(result, list) and bool(result) and isinstance(result[0].get("meta"), dict)
    except (KeyError, TypeError, IndexError):
        return False


def _infer_yahoo_market_state(meta, now_ts=None):
    provider_state = meta.get("marketState")
    if provider_state:
        return str(provider_state).upper()

    periods = meta.get("currentTradingPeriod") or {}
    now_ts = int(time.time() if now_ts is None else now_ts)
    for name, label in (("pre", "PRE"), ("regular", "REGULAR"), ("post", "POST")):
        period = periods.get(name) or {}
        start, end = period.get("start"), period.get("end")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and start <= now_ts < end:
            return label
    return "CLOSED"


def fetch_yahoo_quote(symbol):
    """Fetch one Yahoo regular-session quote with timestamp/state metadata."""
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    path = f"/v8/finance/chart/{encoded_symbol}?interval=1m&range=1d"
    data = _fetch_yahoo_json(path, _valid_yahoo_chart)
    meta = data["chart"]["result"][0]["meta"]

    price = _num(meta.get("regularMarketPrice"))
    previous_close = _first_number(meta, "previousClose", "chartPreviousClose")
    change_pct = _num(meta.get("regularMarketChangePercent"))
    if change_pct is None and price is not None and previous_close not in (None, 0):
        change_pct = (price - previous_close) / previous_close * 100
    if price is None:
        raise ValueError(f"Yahoo quote has no regular-market price: {symbol}")

    provider_market_state = meta.get("marketState")
    return {
        "symbol": meta.get("symbol") or symbol,
        "name": meta.get("shortName") or meta.get("longName") or symbol,
        "price": price,
        "previous_close": previous_close,
        "change_pct": change_pct,
        "day_high": _num(meta.get("regularMarketDayHigh")),
        "day_low": _num(meta.get("regularMarketDayLow")),
        "regular_market_time": meta.get("regularMarketTime"),
        "market_state": _infer_yahoo_market_state(meta),
        "market_state_source": "provider" if provider_market_state else "inferred",
        "provider_market_state": provider_market_state,
        "exchange_timezone": meta.get("exchangeTimezoneName") or meta.get("timezone"),
        "source": "Yahoo Finance chart",
    }


def _valid_yahoo_trending(data):
    try:
        result = data["finance"]["result"]
        return isinstance(result, list) and bool(result) and isinstance(result[0].get("quotes"), list)
    except (KeyError, TypeError, IndexError):
        return False


def fetch_yahoo_trending(region="US", limit=10):
    """Return Yahoo Finance's real trending-symbol feed and source time."""
    if limit <= 0:
        return {"symbols": [], "job_timestamp": None, "start_interval": None}
    safe_region = urllib.parse.quote(region.upper(), safe="")
    path = f"/v1/finance/trending/{safe_region}?count={int(limit)}"
    data = _fetch_yahoo_json(path, _valid_yahoo_trending)
    result = data["finance"]["result"][0]
    symbols = []
    seen = set()
    for quote in result["quotes"]:
        symbol = str(quote.get("symbol") or "").strip() if isinstance(quote, dict) else ""
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
        if len(symbols) >= limit:
            break
    if not symbols:
        raise ValueError("Yahoo trending response contained no symbols")
    return {
        "symbols": symbols,
        "job_timestamp": result.get("jobTimestamp"),
        "start_interval": result.get("startInterval"),
    }


def arrow(change_pct):
    if change_pct is None:
        return ""
    if change_pct > 0:
        return "▲"
    if change_pct < 0:
        return "▼"
    return "-"
