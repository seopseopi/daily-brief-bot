import io
import json
import unittest
import urllib.error
from unittest import mock

from sources import _market, market
from sources._shared import get_failures


NAVER_QUOTE_FIXTURE = {
    "datas": [
        {
            "itemCode": "017670",
            "stockName": "SK텔레콤",
            "closePrice": "90,400",
            "fluctuationsRatio": "0.00",
            "openPrice": "-",
            "highPrice": "-",
            "lowPrice": "-",
            "accumulatedTradingValue": "-",
            "marketStatus": "PREOPEN",
            "marketStatusDetailType": "preopen",
            "marketSessionType": "regularMarket",
            "localTradedAt": "2026-09-11T08:58:00+09:00",
        },
        {
            "itemCode": "009150",
            "stockName": "삼성전기",
            "closePriceRaw": "1400000",
            "fluctuationsRatioRaw": "1.25",
            "highPriceRaw": "1410000",
            "lowPriceRaw": "1380000",
            "marketStatus": "OPEN",
            "localTradedAt": "2026-09-11T09:03:43+09:00",
        },
    ]
}

NAVER_POPULAR_FIXTURE = [
    {"itemcode": "005930", "itemname": "삼성전자", "marketStatus": "OPEN"},
    {"itemcode": "000660", "itemname": "SK하이닉스", "marketStatus": "OPEN"},
]

YAHOO_CHART_FIXTURE = {
    "chart": {
        "result": [
            {
                "meta": {
                    "symbol": "TEST",
                    "shortName": "Test Corp",
                    "regularMarketPrice": 125,
                    "previousClose": 100,
                    "regularMarketDayHigh": 130,
                    "regularMarketDayLow": 120,
                    "regularMarketTime": 1789070400,
                    "marketState": "CLOSED",
                    "exchangeTimezoneName": "America/New_York",
                }
            }
        ],
        "error": None,
    }
}

YAHOO_TRENDING_FIXTURE = {
    "finance": {
        "result": [
            {
                "count": 2,
                "quotes": [{"symbol": "ORCL"}, {"symbol": "ADBE"}],
                "jobTimestamp": 1789074385480,
                "startInterval": 202609102000,
            }
        ],
        "error": None,
    }
}


def _http_error(code, retry_after=None):
    headers = {} if retry_after is None else {"Retry-After": str(retry_after)}
    return urllib.error.HTTPError(
        "https://query1.finance.yahoo.com/test",
        code,
        "test error",
        headers,
        io.BytesIO(b"{}"),
    )


def _quote(name="Test Corp", *, state="CLOSED", change_pct=1.5):
    return {
        "name": name,
        "price": 125.0,
        "change_pct": change_pct,
        "day_high": 130.0,
        "day_low": 120.0,
        "regular_market_time": 1789070400,
        "market_state": state,
        "exchange_timezone": "America/New_York",
        "source": "Yahoo Finance chart",
    }


class MarketTransportTests(unittest.TestCase):
    def test_naver_dash_is_nullable_and_metadata_is_preserved(self):
        payload = json.dumps(NAVER_QUOTE_FIXTURE).encode()
        with mock.patch.object(_market, "_get", return_value=payload):
            quotes = _market.fetch_naver_quotes(["017670", "009150"])

        self.assertEqual(set(quotes), {"017670", "009150"})
        self.assertEqual(quotes["017670"]["price"], 90400.0)
        self.assertIsNone(quotes["017670"]["high"])
        self.assertIsNone(quotes["017670"]["low"])
        self.assertEqual(quotes["017670"]["market_status"], "PREOPEN")
        self.assertEqual(quotes["017670"]["local_traded_at"], "2026-09-11T08:58:00+09:00")
        self.assertEqual(quotes["009150"]["high"], 1410000.0)

    def test_naver_popular_uses_validated_search_top_json(self):
        payload = json.dumps(NAVER_POPULAR_FIXTURE).encode()
        with mock.patch.object(_market, "_get", return_value=payload) as fetch:
            result = _market.fetch_naver_hot_search(limit=2)

        self.assertEqual(result, [("005930", "삼성전자"), ("000660", "SK하이닉스")])
        self.assertIn("orderType=searchTop", fetch.call_args.args[0])

    def test_naver_popular_empty_response_is_validation_failure(self):
        with mock.patch.object(_market, "_get", return_value=b"[]"):
            with self.assertRaisesRegex(ValueError, "no valid stocks"):
                _market.fetch_naver_hot_search()

    def test_yahoo_429_retries_on_query2_and_preserves_time_state(self):
        payload = json.dumps(YAHOO_CHART_FIXTURE).encode()
        with (
            mock.patch.object(_market, "_get", side_effect=[_http_error(429, 0), payload]) as fetch,
            mock.patch.object(_market.time, "sleep") as sleep,
        ):
            quote = _market.fetch_yahoo_quote("TEST")

        self.assertIn("query1.finance.yahoo.com", fetch.call_args_list[0].args[0])
        self.assertIn("query2.finance.yahoo.com", fetch.call_args_list[1].args[0])
        sleep.assert_called_once_with(0.0)
        self.assertEqual(quote["change_pct"], 25.0)
        self.assertEqual(quote["regular_market_time"], 1789070400)
        self.assertEqual(quote["market_state"], "CLOSED")
        self.assertEqual(quote["market_state_source"], "provider")

    def test_yahoo_trending_keeps_provider_timestamp(self):
        payload = json.dumps(YAHOO_TRENDING_FIXTURE).encode()
        with mock.patch.object(_market, "_get", return_value=payload):
            result = _market.fetch_yahoo_trending(limit=2)

        self.assertEqual(result["symbols"], ["ORCL", "ADBE"])
        self.assertEqual(result["job_timestamp"], 1789074385480)


class MarketSectionTests(unittest.TestCase):
    def setUp(self):
        get_failures()

    def tearDown(self):
        get_failures()

    def test_holdings_survive_unavailable_intraday_range_and_hot_source(self):
        configured_symbols = ("017670", "009150")
        quotes = {
            code: {
                "name": f"공급자-{code}",
                "price": 90400.0,
                "change_pct": 0.0,
                "high": None,
                "low": None,
                "market_status": "PREOPEN",
                "local_traded_at": "2026-09-11T08:58:00+09:00",
            }
            for code in configured_symbols
        }
        with (
            mock.patch.object(market, "HOLDINGS_KR", configured_symbols),
            mock.patch.object(_market, "fetch_naver_hot_search", side_effect=ValueError("bad schema")),
            mock.patch.object(_market, "fetch_naver_quotes", return_value=quotes),
        ):
            holdings, hot = market._kr_holdings_and_hot()

        self.assertEqual(len(holdings), len(configured_symbols))
        self.assertEqual(holdings[0][0], "공급자-017670")
        self.assertIn("전일 종가 09/11 08:58", holdings[0][2])
        self.assertNotIn("고가", holdings[0][2])
        self.assertEqual(hot, [])
        self.assertIn("화제종목(국장)", get_failures())

    def test_failed_batch_recovers_quotes_per_symbol(self):
        first = {"017670": {"price": 1.0}}

        def fetch(codes):
            if len(codes) > 1:
                raise OSError("batch failed")
            if codes == ["017670"]:
                return first
            raise OSError("one symbol failed")

        with mock.patch.object(_market, "fetch_naver_quotes", side_effect=fetch):
            recovered = market._fetch_kr_quotes_partial(["017670", "009150"])

        self.assertEqual(recovered, first)

    def test_us_hot_comes_from_trending_feed_not_fixed_watchlist(self):
        quotes = {"ORCL": _quote("Oracle"), "ADBE": _quote("Adobe", change_pct=-2.0)}
        with (
            mock.patch.object(
                _market,
                "fetch_yahoo_trending",
                return_value={"symbols": ["ORCL", "ADBE"], "job_timestamp": 1},
            ),
            mock.patch.object(_market, "fetch_yahoo_quote", side_effect=lambda symbol: quotes[symbol]),
        ):
            hot = market._us_hot()

        self.assertEqual([item[0] for item in hot], ["Oracle", "Adobe"])
        self.assertIn("트렌딩 1위", hot[0][2])

    def test_us_holding_uses_provider_name(self):
        with (
            mock.patch.object(market, "HOLDINGS_US", ("TEST",)),
            mock.patch.object(_market, "fetch_yahoo_quote", return_value=_quote("Provider Name")),
        ):
            holdings = market._us_holdings()

        self.assertEqual(holdings[0][0], "Provider Name")

    def test_private_holding_symbol_is_not_written_to_error_log(self):
        private_symbol = "PRIVATE1"
        with (
            mock.patch.object(market, "HOLDINGS_US", (private_symbol,)),
            mock.patch.object(
                _market,
                "fetch_yahoo_quote",
                side_effect=OSError(f"failed URL containing {private_symbol}"),
            ),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            market._us_holdings()

        self.assertNotIn(private_symbol, stdout.getvalue())

    def test_overnight_label_states_the_actual_arithmetic(self):
        summary = market._overnight_us_summary(
            {"change_pct": 1.0},
            {"change_pct": -0.5},
        )

        self.assertIn("단순평균 +0.25%", summary[0])
        self.assertIn("산술평균", summary[1])
        self.assertIn("국장 예측", summary[1])


if __name__ == "__main__":
    unittest.main()
