# -*- coding: utf-8 -*-
"""Regression tests for Indian market (.NS / .BO) routing and formatting guardrails.

Covers:
1. DataFetcherManager routing logic: .NS and .BO tickers completely bypass
   Akshare, Baostock, and Tencent providers and short-circuit to YfinanceFetcher.
2. YfinanceFetcher._convert_stock_code early checks for .NS and .BO suffixes
   and returns the string as-is without stripping or forcing A-share/US format.
3. BaostockFetcher._fetch_raw_data early fail-open condition raising DataFetchError.
4. AkshareFetcher._fetch_stock_data defensive validator for international strings.
"""

from data_provider.base import (
    BaseFetcher,
    DataFetchError,
    DataFetcherManager,
    normalize_stock_code,
    _is_in_market,
    _market_tag,
)
from data_provider.yfinance_fetcher import YfinanceFetcher
from data_provider.baostock_fetcher import BaostockFetcher
from data_provider.akshare_fetcher import AkshareFetcher


class _FakeFetcher(BaseFetcher):
    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.priority = priority
        self.called = False
        self.calls = []

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str):
        raise NotImplementedError

    def _normalize_data(self, df, stock_code: str):
        raise NotImplementedError

    def get_daily_data(self, stock_code: str, start_date=None, end_date=None, days=30):
        self.called = True
        self.calls.append(stock_code)
        import pandas as pd
        return pd.DataFrame({
            "date": ["2026-08-28"],
            "open": [2500.0],
            "high": [2550.0],
            "low": [2480.0],
            "close": [2520.0],
            "volume": [1000000],
            "amount": [2520000000.0],
            "pct_chg": [0.8],
        })


class TestIndianStockNormalizationAndMarketTag:
    def test_normalize_stock_code_preserves_indian_suffixes(self):
        assert normalize_stock_code("reliance.ns") == "RELIANCE.NS"
        assert normalize_stock_code("RELIANCE.NS") == "RELIANCE.NS"
        assert normalize_stock_code("500325.bo") == "500325.BO"
        assert normalize_stock_code("500325.BO") == "500325.BO"
        assert normalize_stock_code("infy.ns") == "INFY.NS"
        assert normalize_stock_code("tcs.bo") == "TCS.BO"

    def test_is_in_market_and_market_tag(self):
        assert _is_in_market("RELIANCE.NS") is True
        assert _is_in_market("500325.BO") is True
        assert _is_in_market("INFY.NS") is True
        assert _is_in_market("600519") is False
        assert _is_in_market("AAPL") is False
        assert _is_in_market("00700.HK") is False

        assert _market_tag("RELIANCE.NS") == "in"
        assert _market_tag("500325.BO") == "in"
        assert _market_tag("600519") == "cn"
        assert _market_tag("AAPL") == "us"


class TestYfinanceFetcherIndianCodeConversion:
    def test_convert_stock_code_preserves_ns_and_bo_suffixes(self):
        fetcher = YfinanceFetcher()
        assert fetcher._convert_stock_code("RELIANCE.NS") == "RELIANCE.NS"
        assert fetcher._convert_stock_code("reliance.ns") == "RELIANCE.NS"
        assert fetcher._convert_stock_code("500325.BO") == "500325.BO"
        assert fetcher._convert_stock_code("500325.bo") == "500325.BO"
        assert fetcher._convert_stock_code("TCS.NS") == "TCS.NS"
        assert fetcher._convert_stock_code("INFY.BO") == "INFY.BO"

    def test_convert_stock_code_ashare_unaffected(self):
        fetcher = YfinanceFetcher()
        assert fetcher._convert_stock_code("600519") == "600519.SS"
        assert fetcher._convert_stock_code("000001") == "000001.SZ"
        assert fetcher._convert_stock_code("AAPL") == "AAPL"


class TestBaostockFetcherIndianTickerFailOpen:
    def test_fetch_raw_data_raises_data_fetch_error_for_indian_tickers(self):
        fetcher = BaostockFetcher()
        try:
            fetcher._fetch_raw_data("RELIANCE.NS", "2026-01-01", "2026-08-28")
            assert False, "Expected DataFetchError"
        except DataFetchError as e:
            assert "BaostockFetcher does not support Indian NSE/BSE tickers" in str(e)

        try:
            fetcher._fetch_raw_data("500325.BO", "2026-01-01", "2026-08-28")
            assert False, "Expected DataFetchError"
        except DataFetchError as e:
            assert "BaostockFetcher does not support Indian NSE/BSE tickers" in str(e)


class TestAkshareFetcherDefensiveValidator:
    def test_fetch_stock_data_raises_data_fetch_error_for_international_tickers(self):
        fetcher = AkshareFetcher()
        try:
            fetcher._fetch_stock_data("RELIANCE.NS", "2026-01-01", "2026-08-28")
            assert False, "Expected DataFetchError"
        except DataFetchError as e:
            assert "AkshareFetcher skipping unsupported ticker format" in str(e)

        try:
            fetcher._fetch_stock_data("500325.BO", "2026-01-01", "2026-08-28")
            assert False, "Expected DataFetchError"
        except DataFetchError as e:
            assert "AkshareFetcher skipping unsupported ticker format" in str(e)


class TestDataFetcherManagerIndianRouting:
    def test_routing_bypasses_akshare_baostock_tencent_and_routes_to_yfinance(self):
        akshare = _FakeFetcher("AkshareFetcher", priority=1)
        baostock = _FakeFetcher("BaostockFetcher", priority=2)
        tencent = _FakeFetcher("TencentFetcher", priority=3)
        yfinance = _FakeFetcher("YfinanceFetcher", priority=4)

        manager = DataFetcherManager([akshare, baostock, tencent, yfinance])

        df, source = manager.get_daily_data("RELIANCE.NS", days=30)
        assert source == "YfinanceFetcher"
        assert not df.empty
        assert yfinance.called is True
        assert akshare.called is False
        assert baostock.called is False
        assert tencent.called is False

    def test_routing_bypasses_for_bo_suffix(self):
        akshare = _FakeFetcher("AkshareFetcher", priority=1)
        baostock = _FakeFetcher("BaostockFetcher", priority=2)
        tencent = _FakeFetcher("TencentFetcher", priority=3)
        yfinance = _FakeFetcher("YfinanceFetcher", priority=4)

        manager = DataFetcherManager([akshare, baostock, tencent, yfinance])

        df, source = manager.get_daily_data("500325.BO", days=30)
        assert source == "YfinanceFetcher"
        assert not df.empty
        assert yfinance.called is True
        assert akshare.called is False
        assert baostock.called is False
        assert tencent.called is False


class TestIndianMarketReviewSupport:
    def test_market_review_region_normalization(self):
        from src.utils.market_review_region import (
            normalize_market_review_region_lenient,
            normalize_market_review_region_strict,
            MARKET_REVIEW_REGION_ORDER,
        )
        assert "in" in MARKET_REVIEW_REGION_ORDER
        assert normalize_market_review_region_lenient("in") == "in"
        assert normalize_market_review_region_lenient("us,in") == "us,in"
        assert normalize_market_review_region_strict("in") == "in"
        assert normalize_market_review_region_strict("cn,in") == "cn,in"

    def test_yfinance_fetcher_in_main_indices_mapping(self):
        from unittest.mock import MagicMock
        fetcher = YfinanceFetcher()
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = None
        mock_yf.Ticker.return_value = mock_ticker

        # Call _get_in_main_indices with mocked yf
        indices = fetcher._get_in_main_indices(mock_yf)
        assert mock_yf.Ticker.call_count >= 4
        requested_symbols = [call.args[0] for call in mock_yf.Ticker.call_args_list]
        assert "^NSEI" in requested_symbols
        assert "^BSESN" in requested_symbols

    def test_gemini_litellm_model_normalization(self):
        from src.config import _get_litellm_provider
        assert _get_litellm_provider("gemini-2.0-flash") == "gemini"
        assert _get_litellm_provider("gemini/gemini-2.0-flash") == "gemini"
        assert _get_litellm_provider("claude-3-5-sonnet") == "anthropic"
        assert _get_litellm_provider("deepseek-chat") == "deepseek"

