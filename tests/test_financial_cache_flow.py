from types import SimpleNamespace

import pandas as pd
import requests

import stock_service


def test_get_stock_bundle_uses_cached_financial_context(monkeypatch):
    finnhub_bundle = {
        "quote": {"c": 200, "pc": 190, "dp": 5.26},
        "profile": {"marketCapitalization": 3500},
        "metric": {"epsTTM": 5.0},
        "closes": [100, 110, 120, 130, 140, 150],
        "volumes": [1_000_000] * 6,
        "financials_annual": {"data": []},
        "financials_quarterly": {"data": []},
    }

    cache_payload = {
        "financial": {"latest_period": "2025-12-31", "revenue_b": 100.0},
        "ai_financial_context": {"annual": [{"period_end": "2025-12-31"}], "quarterly": []},
    }

    monkeypatch.setattr(stock_service, "_finnhub_bundle", lambda symbol, api_key: finnhub_bundle)
    monkeypatch.setattr(stock_service, "_get_forecast_from_yahoo", lambda symbol: {})
    monkeypatch.setattr(
        stock_service,
        "_get_prediction_fields_from_yfinance",
        lambda symbol: {
            "eps_forecast": None,
            "next_year_eps_forecast": None,
            "next_quarter_eps_forecast": None,
            "next_earnings_date": None,
        },
    )
    monkeypatch.setattr(stock_service, "_get_recent_news", lambda symbol, api_key, limit=5: [])
    monkeypatch.setattr(stock_service, "get_cached_financial_bundle", lambda symbol, ttl_hours=None: cache_payload)

    called = {"financial": 0, "ctx": 0}

    def fake_financial(symbol):
        called["financial"] += 1
        return {}

    def fake_context(symbol, annual_limit=3, quarterly_limit=4):
        called["ctx"] += 1
        return {"annual": [], "quarterly": []}

    monkeypatch.setattr(stock_service, "_get_financial_from_yfinance", fake_financial)
    monkeypatch.setattr(stock_service, "_build_ai_financial_context_from_yfinance", fake_context)

    out = stock_service.get_stock_bundle("NVDA", "fake_key")

    assert out["financial"]["revenue_b"] == 100.0
    assert out["ai_financial_context"]["annual"][0]["period_end"] == "2025-12-31"
    assert called["financial"] == 0
    assert called["ctx"] == 0


def test_get_stock_bundle_writes_cache_on_miss(monkeypatch):
    finnhub_bundle = {
        "quote": {"c": 100, "pc": 100, "dp": 0},
        "profile": {"marketCapitalization": 1000},
        "metric": {"epsTTM": 2.0},
        "closes": [100] * 260,
        "volumes": [1_000_000] * 260,
        "financials_annual": {"data": []},
        "financials_quarterly": {"data": []},
    }

    monkeypatch.setattr(stock_service, "_finnhub_bundle", lambda symbol, api_key: finnhub_bundle)
    monkeypatch.setattr(stock_service, "_get_forecast_from_yahoo", lambda symbol: {})
    monkeypatch.setattr(
        stock_service,
        "_get_prediction_fields_from_yfinance",
        lambda symbol: {
            "eps_forecast": None,
            "next_year_eps_forecast": None,
            "next_quarter_eps_forecast": None,
            "next_earnings_date": None,
        },
    )
    monkeypatch.setattr(stock_service, "_get_recent_news", lambda symbol, api_key, limit=5: [])
    monkeypatch.setattr(stock_service, "get_cached_financial_bundle", lambda symbol, ttl_hours=None: None)

    expected_financial = {"latest_period": "2025-12-31", "revenue_b": 88.0}
    expected_ctx = {"annual": [{"period_end": "2025-12-31"}], "quarterly": []}

    monkeypatch.setattr(stock_service, "_get_financial_from_yfinance", lambda symbol: expected_financial)
    monkeypatch.setattr(
        stock_service,
        "_build_ai_financial_context_from_yfinance",
        lambda symbol, annual_limit=3, quarterly_limit=4: expected_ctx,
    )

    writes = {}

    def fake_set(symbol, financial, ai_financial_context):
        writes["symbol"] = symbol
        writes["financial"] = financial
        writes["ai_financial_context"] = ai_financial_context

    monkeypatch.setattr(stock_service, "set_cached_financial_bundle", fake_set)

    out = stock_service.get_stock_bundle("AMD", "fake_key")

    assert out["financial"] == expected_financial
    assert out["ai_financial_context"] == expected_ctx
    assert writes["symbol"] == "AMD"
    assert writes["financial"] == expected_financial
    assert writes["ai_financial_context"] == expected_ctx


def test_get_stock_bundle_uses_yfinance_realtime_when_finnhub_key_missing(monkeypatch):
    def _unexpected_finnhub_bundle(symbol, api_key):
        raise AssertionError("finnhub should not be called when key is empty")

    history = pd.DataFrame(
        {
            "Close": [100.0, 110.0, 120.0],
            "Volume": [1_000_000, 2_000_000, 3_000_000],
        }
    )
    fake_ticker = SimpleNamespace(
        fast_info={
            "lastPrice": 120.0,
            "previousClose": 110.0,
            "marketCap": 500_000_000_000,
        },
        info={"trailingPE": 30.0},
        history=lambda period="2y", interval="1d", auto_adjust=False: history,
    )

    monkeypatch.setattr(stock_service, "_finnhub_bundle", _unexpected_finnhub_bundle)
    monkeypatch.setattr(stock_service, "_get_forecast_from_yahoo", lambda symbol: {})
    monkeypatch.setattr(
        stock_service,
        "_get_prediction_fields_from_yfinance",
        lambda symbol: {
            "eps_forecast": None,
            "next_year_eps_forecast": None,
            "next_quarter_eps_forecast": None,
            "next_earnings_date": None,
        },
    )
    monkeypatch.setattr(stock_service, "_get_recent_news", lambda symbol, api_key, limit=5: [])
    monkeypatch.setattr(
        stock_service,
        "get_cached_financial_bundle",
        lambda symbol, ttl_hours=None: {"financial": {}, "ai_financial_context": {"annual": [], "quarterly": []}},
    )
    monkeypatch.setattr(stock_service, "yf", SimpleNamespace(Ticker=lambda symbol: fake_ticker), raising=False)

    out = stock_service.get_stock_bundle("AAPL", "")

    assert out["realtime"]["price"] == 120.0
    assert out["realtime"]["change_pct"] == 9.09
    assert out["realtime"]["market_cap_b"] == 500.0
    assert out["realtime"]["pe_ttm"] == 30.0


def _http_error_with_status(code, message):
    err = requests.HTTPError(message)
    err.response = SimpleNamespace(status_code=code)
    return err


def test_get_stock_bundle_surfaces_http_status_in_warnings(monkeypatch):
    monkeypatch.setattr(stock_service, "_finnhub_bundle", lambda symbol, api_key: {})
    monkeypatch.setattr(stock_service, "_get_realtime_from_yfinance", lambda symbol: {"price": 100.0})
    monkeypatch.setattr(
        stock_service,
        "get_cached_financial_bundle",
        lambda symbol, ttl_hours=None: {"financial": {}, "ai_financial_context": {"annual": [], "quarterly": []}},
    )
    monkeypatch.setattr(
        stock_service,
        "_get_forecast_from_yahoo",
        lambda symbol: (_ for _ in ()).throw(_http_error_with_status(429, "Too Many Requests")),
    )
    monkeypatch.setattr(
        stock_service,
        "_get_prediction_fields_from_yfinance",
        lambda symbol: {
            "currency": None,
            "eps_forecast": None,
            "next_year_eps_forecast": None,
            "next_quarter_eps_forecast": None,
            "next_earnings_date": None,
        },
    )
    monkeypatch.setattr(stock_service, "_get_recent_news", lambda symbol, api_key, limit=5: [])
    monkeypatch.setattr(
        stock_service,
        "_build_expectation_guidance_snapshot",
        lambda symbol, news=None, **kwargs: {},
    )

    out = stock_service.get_stock_bundle("NVDA", "")

    assert isinstance(out.get("warnings"), list)
    assert any(item.get("source") == "yahoo.forecast" and item.get("status_code") == 429 for item in out["warnings"])


def test_yahoo_quote_summary_collects_http_status(monkeypatch):
    def _raise_http(*args, **kwargs):
        raise _http_error_with_status(404, "Not Found")

    monkeypatch.setattr(stock_service.requests, "get", _raise_http)
    token = stock_service._start_issue_collection()
    try:
        out = stock_service._yahoo_quote_summary("NVDA", ["summaryDetail"])
    finally:
        issues = stock_service._finish_issue_collection(token)

    assert out == {}
    assert any(item.get("source") == "yahoo.quote_summary" and item.get("status_code") == 404 for item in issues)
