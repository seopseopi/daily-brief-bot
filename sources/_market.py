"""마켓 데이터 공용 유틸리티 (stdlib만 사용).

get_market() 전용 헬퍼. 전부 무료 공개 엔드포인트:
  - 네이버금융 realtime API (국장 지수/개별종목)
  - 네이버금융 인기검색 종목 페이지 (화제종목 — 검색량 기준)
  - 네이버금융 환율 페이지
  - 야후 파이낸스 chart API (미장 지수/종목/금리/VIX)
"""

import html
import json
import re
import urllib.request

USER_AGENT = "MorningBriefBot/1.0 (+https://github.com/seopseopi/daily-brief-bot)"
TIMEOUT = 8


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return res.read()


def _num(s):
    """'1,234.5' -> 1234.5"""
    return float(str(s).replace(",", ""))


def fetch_naver_quotes(codes):
    """국장 지수/개별종목 공용. codes는 'KOSPI','KOSDAQ' 또는 종목코드 리스트.

    반환: {code: {"name", "price", "change_pct", "high", "low", "value"}}
    """
    is_index = all(c.isalpha() for c in codes)
    kind = "index" if is_index else "stock"
    url = f"https://polling.finance.naver.com/api/realtime/domestic/{kind}/{','.join(codes)}"
    data = json.loads(_get(url))
    out = {}
    for item in data.get("datas", []):
        out[item["itemCode"]] = {
            "name": item["stockName"],
            "price": _num(item["closePrice"]),
            "change_pct": _num(item["fluctuationsRatio"]),
            "high": _num(item["highPrice"]),
            "low": _num(item["lowPrice"]),
            "value": item.get("accumulatedTradingValue", ""),
        }
    return out


def fetch_naver_hot_search(limit=10):
    """네이버금융 '인기검색 종목' — 화제종목의 검색량 기준 소스."""
    raw = _get("https://finance.naver.com/sise/lastsearch2.naver")
    text = raw.decode("euc-kr", errors="replace")
    pairs = re.findall(r'<a href="/item/main\.naver\?code=(\d+)"[^>]*>([^<]+)</a>', text)
    return pairs[:limit]


def fetch_naver_fx():
    """USD/JPY(100엔)/CNY 원화 환율. 반환: {"USD": float, "JPY100": float, "CNY": float}"""
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
                result[key] = _num(sale_m.group(1))
    return result


def fetch_yahoo_quote(symbol):
    """야후 파이낸스 chart API. 반환: {"price", "change_pct", "day_high", "day_low"}"""
    from urllib.parse import quote

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
    data = json.loads(_get(url))
    meta = data["chart"]["result"][0]["meta"]
    return {
        "price": meta["regularMarketPrice"],
        "change_pct": meta.get("regularMarketChangePercent", 0.0),
        "day_high": meta.get("regularMarketDayHigh"),
        "day_low": meta.get("regularMarketDayLow"),
    }


def arrow(change_pct):
    if change_pct > 0:
        return "▲"
    if change_pct < 0:
        return "▼"
    return "-"
