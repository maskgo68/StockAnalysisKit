from types import SimpleNamespace

import pandas as pd
import re

import stock_service


def _make_income_stmt(columns_to_values):
    # columns_to_values: {timestamp: {row_label: value}}
    cols = list(columns_to_values.keys())
    row_labels = []
    for v in columns_to_values.values():
        for k in v.keys():
            if k not in row_labels:
                row_labels.append(k)

    data = {}
    for col in cols:
        values = []
        mapping = columns_to_values[col]
        for row in row_labels:
            values.append(mapping.get(row))
        data[pd.Timestamp(col)] = values
    return pd.DataFrame(data, index=row_labels)


def test_get_financial_from_yfinance_quarterly(monkeypatch):
    quarterly = _make_income_stmt(
        {
            "2025-10-26": {
                "Total Revenue": 57_000_000_000,
                "Gross Profit": 41_842_000_000,
                "Operating Income": 36_010_000_000,
                "Net Income": 31_910_000_000,
                "Diluted EPS": 1.30,
            },
            "2024-10-27": {
                "Total Revenue": 35_082_000_000,
                "Gross Profit": 26_000_000_000,
                "Operating Income": 21_869_000_000,
                "Net Income": 19_309_000_000,
                "Diluted EPS": 0.78,
            },
        }
    )

    fake_ticker = SimpleNamespace(
        quarterly_income_stmt=quarterly,
        quarterly_financials=quarterly,
        income_stmt=pd.DataFrame(),
        financials=pd.DataFrame(),
    )
    monkeypatch.setattr(stock_service, "yf", SimpleNamespace(Ticker=lambda symbol: fake_ticker), raising=False)

    result = stock_service._get_financial_from_yfinance("NVDA")

    assert result["latest_period"] == "2025-10-26"
    assert result["latest_period_type"] == "quarterly"
    assert result["revenue_b"] == 57.0
    assert result["net_income_b"] == 31.91
    assert result["eps"] == 1.3
    assert result["revenue_yoy_pct"] == 62.48


def test_get_financial_from_yfinance_includes_roe_from_balance_sheet(monkeypatch):
    quarterly = _make_income_stmt(
        {
            "2025-10-26": {
                "Total Revenue": 10_000_000_000,
                "Gross Profit": 5_000_000_000,
                "Operating Income": 3_000_000_000,
                "Net Income": 1_500_000_000,
                "Diluted EPS": 0.75,
            },
            "2024-10-27": {
                "Total Revenue": 8_000_000_000,
                "Net Income": 1_200_000_000,
            },
        }
    )
    quarterly_balance = _make_income_stmt(
        {
            "2025-10-26": {"Stockholders Equity": 5_000_000_000},
            "2024-10-27": {"Stockholders Equity": 4_600_000_000},
        }
    )

    fake_ticker = SimpleNamespace(
        quarterly_income_stmt=quarterly,
        quarterly_financials=quarterly,
        quarterly_balance_sheet=quarterly_balance,
        quarterly_balancesheet=quarterly_balance,
        income_stmt=pd.DataFrame(),
        financials=pd.DataFrame(),
        balance_sheet=pd.DataFrame(),
        balancesheet=pd.DataFrame(),
        info={},
    )
    monkeypatch.setattr(stock_service, "yf", SimpleNamespace(Ticker=lambda symbol: fake_ticker), raising=False)

    result = stock_service._get_financial_from_yfinance("NVDA")

    assert result["roe_pct"] == 30.0


def test_get_financial_from_yfinance_falls_back_to_annual(monkeypatch):
    annual = _make_income_stmt(
        {
            "2025-12-31": {
                "Total Revenue": 147_810_000_000,
                "Gross Profit": 111_529_000_000,
                "Operating Income": 91_406_000_000,
                "Net Income": 77_110_000_000,
                "Diluted EPS": 3.14,
            },
            "2024-12-31": {
                "Total Revenue": 90_000_000_000,
                "Gross Profit": 66_000_000_000,
                "Operating Income": 50_000_000_000,
                "Net Income": 40_000_000_000,
                "Diluted EPS": 1.8,
            },
        }
    )

    fake_ticker = SimpleNamespace(
        quarterly_income_stmt=pd.DataFrame(),
        quarterly_financials=pd.DataFrame(),
        income_stmt=annual,
        financials=annual,
    )
    monkeypatch.setattr(stock_service, "yf", SimpleNamespace(Ticker=lambda symbol: fake_ticker), raising=False)

    result = stock_service._get_financial_from_yfinance("NVDA")

    assert result["latest_period"] == "2025-12-31"
    assert result["latest_period_type"] == "annual"
    assert result["revenue_b"] == 147.81
    assert result["net_income_b"] == 77.11


def test_get_financial_from_yfinance_fills_eps_from_shares(monkeypatch):
    quarterly = _make_income_stmt(
        {
            "2025-12-31": {
                "Total Revenue": 10_270_000_000,
                "Gross Profit": 5_570_000_000,
                "Operating Income": 1_752_000_000,
                "Net Income": 1_510_000_000,
                "Diluted EPS": float("nan"),
                "Basic EPS": float("nan"),
                "Diluted Average Shares": float("nan"),
                "Basic Average Shares": float("nan"),
            },
            "2024-12-31": {
                "Total Revenue": 7_660_000_000,
                "Net Income": 482_000_000,
            },
        }
    )

    earnings_dates = pd.DataFrame(
        {"Reported EPS": [0.96, 1.09]},
        index=[pd.Timestamp("2025-05-06"), pd.Timestamp("2025-02-04")],
    )
    fake_ticker = SimpleNamespace(
        quarterly_income_stmt=quarterly,
        quarterly_financials=quarterly,
        income_stmt=pd.DataFrame(),
        financials=pd.DataFrame(),
        fast_info={"shares": 1_630_000_000},
        info={"sharesOutstanding": 1_630_000_000},
        get_earnings_dates=lambda limit=12: earnings_dates,
    )
    monkeypatch.setattr(stock_service, "yf", SimpleNamespace(Ticker=lambda symbol: fake_ticker), raising=False)

    result = stock_service._get_financial_from_yfinance("AMD")
    assert result["latest_period"] == "2025-12-31"
    assert result["eps"] == 0.93


def test_get_financial_from_yfinance_skips_empty_latest_quarter(monkeypatch):
    quarterly = _make_income_stmt(
        {
            "2025-12-31": {
                "Total Revenue": float("nan"),
                "Gross Profit": float("nan"),
                "Operating Income": float("nan"),
                "Net Income": float("nan"),
                "Diluted EPS": 1.63,
            },
            "2025-09-30": {
                "Total Revenue": 7_692_100_000,
                "Gross Profit": 4_493_060_000,
                "Operating Income": 1_518_880_000,
                "Net Income": 1_195_580_000,
                "Diluted EPS": 0.75,
            },
            "2024-09-30": {
                "Total Revenue": 7_372_980_000,
                "Gross Profit": 4_365_140_000,
                "Operating Income": 1_566_430_000,
                "Net Income": 1_456_490_000,
                "Diluted EPS": 0.89,
            },
        }
    )

    fake_ticker = SimpleNamespace(
        quarterly_income_stmt=quarterly,
        quarterly_financials=quarterly,
        income_stmt=pd.DataFrame(),
        financials=pd.DataFrame(),
    )
    monkeypatch.setattr(stock_service, "yf", SimpleNamespace(Ticker=lambda symbol: fake_ticker), raising=False)

    result = stock_service._get_financial_from_yfinance("TER")

    assert result["latest_period"] == "2025-09-30"
    assert result["latest_period_type"] == "quarterly"
    assert result["revenue_b"] == 7.69
    assert result["net_income_b"] == 1.2
    assert result["eps"] == 0.75


def test_get_forecast_from_yahoo_uses_quote_summary_next_qtr_fallback(monkeypatch):
    monkeypatch.setattr(
        stock_service,
        "_parse_yahoo_pages",
        lambda symbol: {
            "display_metrics": {},
            "quote_summary": {},
            "analysis_eps_trend": {"current_year_eps": None, "next_qtr_eps": None, "next_year_eps": None},
        },
        raising=False,
    )

    def _forbid_yfinance_eps_fallback(_symbol):
        raise AssertionError("yfinance EPS fallback should not be called from _get_forecast_from_yahoo")

    def _forbid_extra_analysis_request(_symbol):
        raise AssertionError("analysis page should be reused instead of requesting twice")

    monkeypatch.setattr(
        stock_service,
        "_yahoo_quote_summary",
        lambda symbol, modules: {
            "earningsTrend": {"trend": [{"period": "+1q", "epsEstimate": {"raw": 1.93}}]}
        },
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_extract_eps_trend_current_estimate",
        _forbid_extra_analysis_request,
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_extract_next_quarter_eps_from_yfinance",
        _forbid_yfinance_eps_fallback,
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_extract_next_year_eps_from_yfinance",
        _forbid_yfinance_eps_fallback,
        raising=False,
    )

    out = stock_service._get_forecast_from_yahoo("TER")

    assert out["next_quarter_eps_forecast"] == 1.93


def test_get_forecast_from_yahoo_includes_ev_ebitda_and_ps_from_display_metrics(monkeypatch):
    monkeypatch.setattr(
        stock_service,
        "_parse_yahoo_pages",
        lambda symbol: {
            "display_metrics": {
                "Forward P/E": 35.2,
                "PEG Ratio (5yr expected)": 1.7,
                "Enterprise Value/EBITDA": 23.46,
                "Price/Sales (ttm)": 14.31,
                "Price/Book (mrq)": 10.28,
            },
            "quote_summary": {},
        },
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_extract_eps_trend_current_estimate",
        lambda symbol: {"current_year_eps": None, "next_qtr_eps": None},
        raising=False,
    )

    captured = {}

    def fake_quote_summary(symbol, modules):
        captured["modules"] = modules
        return {
            "defaultKeyStatistics": {"enterpriseToEbitda": {"raw": 21.1}},
            "summaryDetail": {"priceToSalesTrailing12Months": {"raw": 12.9}},
        }

    monkeypatch.setattr(stock_service, "_yahoo_quote_summary", fake_quote_summary, raising=False)

    out = stock_service._get_forecast_from_yahoo("NVDA")

    assert "summaryDetail" in captured["modules"]
    assert out["ev_to_ebitda"] == 23.46
    assert out["ps"] == 14.31
    assert out["pb"] == 10.28


def test_get_forecast_from_yahoo_falls_back_to_quote_summary_for_ev_ebitda_and_ps(monkeypatch):
    monkeypatch.setattr(stock_service, "_parse_yahoo_pages", lambda symbol: {"display_metrics": {}, "quote_summary": {}}, raising=False)
    monkeypatch.setattr(
        stock_service,
        "_extract_eps_trend_current_estimate",
        lambda symbol: {"current_year_eps": None, "next_qtr_eps": None},
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_yahoo_quote_summary",
        lambda symbol, modules: {
            "defaultKeyStatistics": {"enterpriseToEbitda": {"raw": 19.876}},
            "summaryDetail": {"priceToSalesTrailing12Months": {"raw": 8.4321}},
        },
        raising=False,
    )
    out = stock_service._get_forecast_from_yahoo("AMD")

    assert out["ev_to_ebitda"] == 19.88
    assert out["ps"] == 8.43


def test_get_forecast_from_yahoo_includes_next_year_eps_forecast(monkeypatch):
    monkeypatch.setattr(
        stock_service,
        "_parse_yahoo_pages",
        lambda symbol: {
            "display_metrics": {
                "Next Year EPS Estimate": 8.76,
            },
            "quote_summary": {},
        },
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_extract_eps_trend_current_estimate",
        lambda symbol: {"current_year_eps": None, "next_qtr_eps": None, "next_year_eps": None},
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_yahoo_quote_summary",
        lambda symbol, modules: {
            "earningsTrend": {"trend": [{"period": "+1y", "epsEstimate": {"raw": 7.11}}]},
        },
        raising=False,
    )
    out = stock_service._get_forecast_from_yahoo("NVDA")

    assert out["next_year_eps_forecast"] == 8.76


def test_get_forecast_from_yahoo_falls_back_to_quote_summary_next_year_eps(monkeypatch):
    monkeypatch.setattr(stock_service, "_parse_yahoo_pages", lambda symbol: {"display_metrics": {}, "quote_summary": {}}, raising=False)
    monkeypatch.setattr(
        stock_service,
        "_extract_eps_trend_current_estimate",
        lambda symbol: {"current_year_eps": None, "next_qtr_eps": None, "next_year_eps": None},
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_yahoo_quote_summary",
        lambda symbol, modules: {
            "earningsTrend": {"trend": [{"period": "+1y", "epsEstimate": {"raw": 9.1234}}]},
        },
        raising=False,
    )
    out = stock_service._get_forecast_from_yahoo("AMD")

    assert out["next_year_eps_forecast"] == 9.12


def test_build_ai_financial_context_from_yfinance_uses_statement_frames(monkeypatch):
    quarterly_income = _make_income_stmt(
        {
            "2025-10-26": {
                "Total Revenue": 57_000_000_000,
                "Gross Profit": 41_842_000_000,
                "Operating Income": 36_010_000_000,
                "Net Income": 31_910_000_000,
                "Diluted EPS": 1.30,
            },
            "2025-07-27": {
                "Total Revenue": 44_100_000_000,
                "Gross Profit": 31_700_000_000,
                "Operating Income": 25_500_000_000,
                "Net Income": 22_900_000_000,
                "Diluted EPS": 0.96,
            },
        }
    )
    annual_income = _make_income_stmt(
        {
            "2025-12-31": {
                "Total Revenue": 147_810_000_000,
                "Gross Profit": 111_529_000_000,
                "Operating Income": 91_406_000_000,
                "Net Income": 77_110_000_000,
                "Diluted EPS": 3.14,
            },
            "2024-12-31": {
                "Total Revenue": 90_000_000_000,
                "Gross Profit": 66_000_000_000,
                "Operating Income": 50_000_000_000,
                "Net Income": 40_000_000_000,
                "Diluted EPS": 1.80,
            },
        }
    )
    quarterly_cashflow = _make_income_stmt(
        {
            "2025-10-26": {
                "Operating Cash Flow": 21_000_000_000,
                "Capital Expenditure": -3_000_000_000,
            },
            "2025-07-27": {
                "Operating Cash Flow": 15_000_000_000,
                "Capital Expenditure": -2_000_000_000,
            },
        }
    )
    annual_cashflow = _make_income_stmt(
        {
            "2025-12-31": {
                "Operating Cash Flow": 93_000_000_000,
                "Capital Expenditure": -16_000_000_000,
            },
            "2024-12-31": {
                "Operating Cash Flow": 61_000_000_000,
                "Capital Expenditure": -11_000_000_000,
            },
        }
    )
    quarterly_balance = _make_income_stmt(
        {
            "2025-10-26": {
                "Total Assets": 170_000_000_000,
                "Total Liabilities Net Minority Interest": 70_000_000_000,
                "Stockholders Equity": 100_000_000_000,
            },
            "2025-07-27": {
                "Total Assets": 162_000_000_000,
                "Total Liabilities Net Minority Interest": 66_000_000_000,
                "Stockholders Equity": 96_000_000_000,
            },
        }
    )
    annual_balance = _make_income_stmt(
        {
            "2025-12-31": {
                "Total Assets": 190_000_000_000,
                "Total Liabilities Net Minority Interest": 80_000_000_000,
                "Stockholders Equity": 110_000_000_000,
            },
            "2024-12-31": {
                "Total Assets": 150_000_000_000,
                "Total Liabilities Net Minority Interest": 72_000_000_000,
                "Stockholders Equity": 78_000_000_000,
            },
        }
    )

    fake_ticker = SimpleNamespace(
        quarterly_income_stmt=quarterly_income,
        quarterly_financials=quarterly_income,
        income_stmt=annual_income,
        financials=annual_income,
        quarterly_cashflow=quarterly_cashflow,
        quarterly_cash_flow=quarterly_cashflow,
        cashflow=annual_cashflow,
        cash_flow=annual_cashflow,
        quarterly_balance_sheet=quarterly_balance,
        quarterly_balancesheet=quarterly_balance,
        balance_sheet=annual_balance,
        balancesheet=annual_balance,
    )
    monkeypatch.setattr(stock_service, "yf", SimpleNamespace(Ticker=lambda symbol: fake_ticker), raising=False)

    ctx = stock_service._build_ai_financial_context_from_yfinance("NVDA", annual_limit=3, quarterly_limit=4)

    assert len(ctx["annual"]) == 2
    assert len(ctx["quarterly"]) == 2
    assert ctx["annual"][0]["period_end"] == "2025-12-31"
    assert ctx["annual"][0]["revenue_b"] == 147.81
    assert ctx["annual"][0]["free_cash_flow_b"] == 77.0
    assert ctx["annual"][0]["shareholders_equity_b"] == 110.0
    assert ctx["quarterly"][0]["period_end"] == "2025-10-26"
    assert ctx["quarterly"][0]["fiscal_quarter"] == 4
    assert ctx["quarterly"][0]["revenue_b"] == 57.0
    assert ctx["quarterly"][0]["free_cash_flow_b"] == 18.0
    assert ctx["quarterly"][0]["gross_margin_pct"] == 73.41


def test_get_stock_bundle_uses_yfinance_for_financial(monkeypatch):
    monkeypatch.setattr(stock_service, "get_cached_financial_bundle", lambda symbol, ttl_hours=12: None, raising=False)
    monkeypatch.setattr(stock_service, "set_cached_financial_bundle", lambda symbol, financial, ctx: None, raising=False)

    expected_financial = {
        "latest_period": "2025-10-26",
        "latest_period_type": "quarterly",
        "revenue_b": 57.0,
        "revenue_yoy_pct": 62.48,
        "net_income_b": 31.91,
        "net_income_yoy_pct": 65.26,
        "eps": 1.3,
        "gross_margin_pct": 73.41,
        "operating_margin_pct": 63.18,
        "net_margin_pct": 55.98,
    }

    finnhub_bundle = {
        "quote": {"c": 200, "pc": 190, "dp": 5.26},
        "profile": {"marketCapitalization": 3500},
        "metric": {"epsTTM": 5.0},
        "closes": [100, 110, 120, 130, 140, 150],
        "volumes": [1_000_000] * 6,
        "financials_annual": {"data": []},
        "financials_quarterly": {"data": []},
    }
    expected_ai_context = {
        "annual": [{"period_end": "2025-12-31", "revenue_b": 147.81}],
        "quarterly": [{"period_end": "2025-10-26", "revenue_b": 57.0}],
    }

    monkeypatch.setattr(stock_service, "_finnhub_bundle", lambda symbol, api_key: finnhub_bundle)
    monkeypatch.setattr(stock_service, "_get_financial_from_yfinance", lambda symbol: expected_financial)
    monkeypatch.setattr(
        stock_service,
        "_build_ai_financial_context_from_yfinance",
        lambda symbol, annual_limit=3, quarterly_limit=4: expected_ai_context,
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_get_forecast_from_yahoo",
        lambda symbol: {
            "forward_pe": 30,
            "peg": 1.5,
            "eps_forecast": 6,
            "next_quarter_eps_forecast": 1.7,
            "next_earnings_date": "2026-02-20",
        },
    )
    monkeypatch.setattr(
        stock_service,
        "_get_prediction_fields_from_yfinance",
        lambda symbol: {
            "eps_forecast": 6.2,
            "next_year_eps_forecast": 7.4,
            "next_quarter_eps_forecast": None,
            "next_earnings_date": None,
        },
    )
    monkeypatch.setattr(stock_service, "_get_recent_news", lambda symbol, api_key, limit=5: [])

    bundle = stock_service.get_stock_bundle("NVDA", "fake_key")

    assert bundle["financial"] == expected_financial
    assert bundle["ai_financial_context"] == expected_ai_context
    assert bundle["forecast"]["eps_forecast"] == 6.2
    assert bundle["forecast"]["next_year_eps_forecast"] == 7.4
    assert bundle["forecast"]["next_quarter_eps_forecast"] == 1.7
    assert bundle["forecast"]["next_earnings_date"] == "2026-02-20"
    assert "earnings_analysis" not in bundle


def test_generate_financial_analysis_respects_symbol_order(monkeypatch):
    monkeypatch.setattr(
        stock_service,
        "_build_earnings_focus_commentary",
        lambda stock: f"### {stock['symbol']}\n- manual",
    )

    stocks = [{"symbol": "NVDA"}, {"symbol": "AMD"}]
    text = stock_service.generate_financial_analysis(["AMD", "NVDA"], stocks)

    assert text.startswith("### AMD")
    assert "\n\n### NVDA" in text


def test_generate_financial_analysis_uses_ai_when_configured(monkeypatch):
    monkeypatch.setattr(stock_service, "_generate_financial_analysis_local", lambda symbols, stocks: "local", raising=False)
    monkeypatch.setattr(
        stock_service,
        "_generate_financial_analysis_with_ai",
        lambda symbols, stocks, provider, api_key, model, base_url=None: "ai",
        raising=False,
    )

    text = stock_service.generate_financial_analysis(
        symbols=["NVDA"],
        stocks=[{"symbol": "NVDA"}],
        provider="gemini",
        api_key="k",
        model="m",
    )
    assert text == "ai"


def test_generate_financial_analysis_falls_back_local_when_ai_empty(monkeypatch):
    monkeypatch.setattr(stock_service, "_generate_financial_analysis_local", lambda symbols, stocks: "local", raising=False)
    monkeypatch.setattr(
        stock_service,
        "_generate_financial_analysis_with_ai",
        lambda symbols, stocks, provider, api_key, model, base_url=None: "   ",
        raising=False,
    )

    text = stock_service.generate_financial_analysis(
        symbols=["NVDA"],
        stocks=[{"symbol": "NVDA"}],
        provider="gemini",
        api_key="k",
        model="m",
    )
    assert text == "local"


def test_generate_financial_analysis_uses_exa_search_context_when_configured(monkeypatch):
    monkeypatch.setattr(stock_service, "_generate_financial_analysis_local", lambda symbols, stocks: "local", raising=False)
    monkeypatch.setattr(
        stock_service,
        "_search_with_exa",
        lambda query, api_key, max_results=6, lookback_days=60: [
            {
                "title": "NVIDIA earnings beat expectations",
                "url": "https://example.com/nvda-earnings",
                "published_at": "2026-02-01",
                "source": "Reuters",
                "snippet": "Revenue and EPS both beat.",
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_search_with_tavily",
        lambda query, api_key, max_results=6, lookback_days=60: [],
        raising=False,
    )

    captured = {}

    def fake_call(provider_key, prompt, api_key, model, base_url=None, enable_model_search=True):
        captured["prompt"] = prompt
        captured["enable_model_search"] = enable_model_search
        return "ai", "stop"

    monkeypatch.setattr(stock_service, "_call_ai_once", fake_call, raising=False)

    text = stock_service.generate_financial_analysis(
        symbols=["NVDA"],
        stocks=[{"symbol": "NVDA", "financial": {}, "forecast": {}, "news": [], "ai_financial_context": {"annual": [], "quarterly": []}}],
        provider="gemini",
        api_key="k",
        model="m",
        exa_api_key="exa-k",
    )

    assert text == "ai"
    assert captured["enable_model_search"] is False
    assert "外部搜索结果（由 Exa/Tavily 提供）" in captured["prompt"]
    assert "NVIDIA earnings beat expectations" in captured["prompt"]


def test_generate_ai_investment_advice_falls_back_to_model_search_without_search_api(monkeypatch):
    captured = {}

    def fake_call(provider_key, prompt, api_key, model, base_url=None, enable_model_search=True):
        captured["prompt"] = prompt
        captured["enable_model_search"] = enable_model_search
        return "ok", "stop"

    monkeypatch.setattr(stock_service, "_call_ai_once", fake_call, raising=False)

    text = stock_service.generate_ai_investment_advice(
        symbols=["NVDA"],
        stocks=[
            {
                "symbol": "NVDA",
                "realtime": {},
                "forecast": {},
                "news": [],
                "ai_financial_context": {"annual": [], "quarterly": []},
            }
        ],
        provider="openai",
        api_key="k",
        model="m",
    )

    assert text == "ok"
    assert captured["enable_model_search"] is True
    assert "外部搜索结果（由 Exa/Tavily 提供）" not in captured["prompt"]


def test_generate_ai_investment_advice_uses_tavily_when_exa_missing(monkeypatch):
    monkeypatch.setattr(stock_service, "_search_with_exa", lambda query, api_key, max_results=6, lookback_days=30: [], raising=False)
    monkeypatch.setattr(
        stock_service,
        "_search_with_tavily",
        lambda query, api_key, max_results=6, lookback_days=30: [
            {
                "title": "AMD updates AI roadmap",
                "url": "https://example.com/amd-roadmap",
                "published_at": "2026-02-08",
                "source": "Bloomberg",
                "snippet": "Management highlighted new accelerator timeline.",
            }
        ],
        raising=False,
    )

    captured = {}

    def fake_call(provider_key, prompt, api_key, model, base_url=None, enable_model_search=True):
        captured["prompt"] = prompt
        captured["enable_model_search"] = enable_model_search
        return "ok", "stop"

    monkeypatch.setattr(stock_service, "_call_ai_once", fake_call, raising=False)

    text = stock_service.generate_ai_investment_advice(
        symbols=["AMD"],
        stocks=[
            {
                "symbol": "AMD",
                "realtime": {},
                "forecast": {},
                "news": [],
                "ai_financial_context": {"annual": [], "quarterly": []},
            }
        ],
        provider="gemini",
        api_key="k",
        model="m",
        tavily_api_key="tavily-k",
    )

    assert text == "ok"
    assert captured["enable_model_search"] is False
    assert "AMD updates AI roadmap" in captured["prompt"]


def test_reference_lines_are_kept_as_plain_text():
    text = """## 参考来源
1. Nvidia Unveils Roadmap: From Blackwell Ultra to Vera Rubin, StorageReview, 2025-09-10.
2. Intel, AMD Warn China Customers Of Months-Long CPU Delays, Yahoo Finance/Reuters, 2026-02-07.
"""

    out = stock_service._ensure_reference_links(text, stocks=[{"symbol": "NVDA", "news": []}])

    assert out.strip() == text.strip()
    assert "Nvidia Unveils Roadmap: From Blackwell Ultra to Vera Rubin" in out
    assert "Intel, AMD Warn China Customers Of Months-Long CPU Delays" in out


def test_reference_links_keep_existing_markdown_links():
    text = """## 参考来源
- [NVIDIA News](https://example.com/nvda)
"""

    out = stock_service._ensure_reference_links(text)

    assert out.strip() == text.strip()


def test_reference_lines_keep_header_with_suffix_text():
    text = """5. 参考来源（近60天）
1. Nvidia Unveils Roadmap: From Blackwell Ultra to Vera Rubin, StorageReview, 2025-09-10.
"""

    out = stock_service._ensure_reference_links(text, stocks=[{"symbol": "NVDA", "news": []}])

    assert out.strip() == text.strip()


def test_generate_ai_investment_advice_keeps_reference_plain_text(monkeypatch):
    monkeypatch.setattr(
        stock_service,
        "_call_ai_once",
        lambda provider_key, prompt, api_key, model, base_url=None: (
            "## 参考来源\n1. Nvidia Unveils Roadmap: From Blackwell Ultra to Vera Rubin, StorageReview, 2025-09-10.",
            "stop",
        ),
        raising=False,
    )

    text = stock_service.generate_ai_investment_advice(
        symbols=["NVDA"],
        stocks=[
            {
                "symbol": "NVDA",
                "realtime": {},
                "forecast": {},
                "news": [],
                "ai_financial_context": {"annual": [], "quarterly": []},
            }
        ],
        provider="openai",
        api_key="k",
        model="m",
    )

    assert text.strip() == "## 参考来源\n1. Nvidia Unveils Roadmap: From Blackwell Ultra to Vera Rubin, StorageReview, 2025-09-10."


def test_generate_financial_analysis_keeps_reference_plain_text(monkeypatch):
    monkeypatch.setattr(stock_service, "_generate_financial_analysis_local", lambda symbols, stocks: "local", raising=False)
    monkeypatch.setattr(
        stock_service,
        "_generate_financial_analysis_with_ai",
        lambda symbols, stocks, provider, api_key, model, base_url=None: (
            "## 参考来源\n1. Intel, AMD Warn China Customers Of Months-Long CPU Delays, Yahoo Finance/Reuters, 2026-02-07."
        ),
        raising=False,
    )

    text = stock_service.generate_financial_analysis(
        symbols=["NVDA"],
        stocks=[{"symbol": "NVDA"}],
        provider="gemini",
        api_key="k",
        model="m",
    )

    assert text.strip() == "## 参考来源\n1. Intel, AMD Warn China Customers Of Months-Long CPU Delays, Yahoo Finance/Reuters, 2026-02-07."


def test_generate_financial_analysis_keeps_reference_header_suffix_plain_text(monkeypatch):
    monkeypatch.setattr(stock_service, "_generate_financial_analysis_local", lambda symbols, stocks: "local", raising=False)
    monkeypatch.setattr(
        stock_service,
        "_generate_financial_analysis_with_ai",
        lambda symbols, stocks, provider, api_key, model, base_url=None: (
            "5. 参考来源（近60天）\n1. Intel, AMD Warn China Customers Of Months-Long CPU Delays, Yahoo Finance/Reuters, 2026-02-07."
        ),
        raising=False,
    )

    text = stock_service.generate_financial_analysis(
        symbols=["NVDA"],
        stocks=[{"symbol": "NVDA"}],
        provider="gemini",
        api_key="k",
        model="m",
    )

    assert text.strip() == "5. 参考来源（近60天）\n1. Intel, AMD Warn China Customers Of Months-Long CPU Delays, Yahoo Finance/Reuters, 2026-02-07."


def test_run_ai_with_auto_continue_returns_error_for_unsupported_provider():
    text, err = stock_service._run_ai_with_auto_continue(
        provider="unknown",
        prompt="p",
        api_key="k",
        model="m",
        continue_prompt="继续",
    )

    assert text == ""
    assert err == "不支持的 AI Provider: unknown"


def test_run_ai_with_auto_continue_auto_continues_on_truncation(monkeypatch):
    prompts = []

    def fake_call(provider_key, prompt, api_key, model, base_url=None, enable_model_search=True):
        prompts.append(prompt)
        if len(prompts) == 1:
            return "first part", "length"
        return "second part", "stop"

    monkeypatch.setattr(stock_service, "_call_ai_once_with_search_flag", fake_call, raising=False)

    text, err = stock_service._run_ai_with_auto_continue(
        provider="openai",
        prompt="start prompt",
        api_key="k",
        model="m",
        continue_prompt="continue prompt",
        enable_model_search=False,
    )

    assert err is None
    assert text == "first part\n\nsecond part"
    assert prompts == ["start prompt", "continue prompt"]


def test_reference_links_do_not_fall_back_to_google_search_when_unmatched():
    text = """## 参考来源
1. Completely Unrelated Headline, Unknown, 2026-02-01.
"""

    out = stock_service._ensure_reference_links(
        text,
        stocks=[{"symbol": "NVDA", "news": [{"title": "Known title", "link": "https://example.com/known"}]}],
    )

    assert "google.com/search" not in out
    assert "Completely Unrelated Headline" in out


def test_build_ai_prompt_contains_financial_history_block():
    stocks = [
        {
            "symbol": "NVDA",
            "realtime": {
                "change_pct": 1.2,
                "change_5d_pct": 2.1,
                "change_20d_pct": 5.1,
                "change_250d_pct": 88.0,
                "pe_ttm": 45.2,
            },
            "forecast": {
                "forward_pe": 34.1,
                "peg": 1.9,
                "next_quarter_eps_forecast": 0.68,
                "next_earnings_date": "2026-02-26",
            },
            "news": [],
            "ai_financial_context": {
                "annual": [
                    {
                        "period_end": "2025-12-31",
                        "revenue_b": 120.0,
                        "gross_margin_pct": 50.0,
                        "operating_margin_pct": 30.0,
                        "net_income_b": 30.0,
                        "eps_diluted": 6.2,
                        "operating_cash_flow_b": 42.0,
                        "free_cash_flow_b": 36.0,
                    }
                ],
                "quarterly": [
                    {
                        "period_end": "2025-12-31",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 4,
                        "revenue_b": 35.0,
                        "gross_margin_pct": 51.4,
                        "operating_margin_pct": 28.6,
                        "net_income_b": 9.0,
                        "eps_diluted": 1.8,
                    }
                ],
            },
        }
    ]

    prompt = stock_service._build_ai_prompt(["NVDA"], stocks)

    assert "AI Financial Context - Annual (3Y)" in prompt
    assert "AI Financial Context - Quarterly (4Q)" in prompt
    assert "2025-12-31" in prompt
    assert "Revenue(B (Local Currency))=120.0" in prompt


def test_build_target_price_prompt_requires_bull_base_bear_ranges():
    stocks = [
        {
            "symbol": "NVDA",
            "realtime": {
                "price": 892.4,
                "pe_ttm": 45.2,
                "change_pct": 1.2,
                "change_20d_pct": 5.1,
            },
            "forecast": {
                "forward_pe": 34.1,
                "peg": 1.9,
                "eps_forecast": 4.86,
                "next_year_eps_forecast": 6.02,
                "next_quarter_eps_forecast": 1.35,
                "next_earnings_date": "2026-02-26",
            },
            "news": [],
            "ai_financial_context": {
                "annual": [
                    {
                        "period_end": "2025-12-31",
                        "revenue_b": 120.0,
                        "net_income_b": 30.0,
                    }
                ],
                "quarterly": [
                    {
                        "period_end": "2025-12-31",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 4,
                        "revenue_b": 35.0,
                        "net_income_b": 9.0,
                    }
                ],
            },
        }
    ]

    prompt = stock_service._build_target_price_prompt(["NVDA"], stocks)

    assert "bull / base / bear" in prompt
    assert "估值区间" in prompt
    assert "目标价区间" in prompt
    assert "关键假设" in prompt
    assert "不需要精确到小数点" in prompt
    assert "目标价 = Forward PE × EPS" in prompt
    assert "EPS 仅使用 next_year_eps_forecast" in prompt
    assert "若缺失则回退到 next_quarter_eps_forecast × 4" in prompt
    assert "A/B/C 三锚点权重固定为 40% / 35% / 25%" in prompt
    assert "Bull / Base / Bear 的 PE 偏移固定为 +15% / 0 / -15%" in prompt
    assert "情绪修正上限为 ±5%" in prompt
    assert "输出只展示最终目标PE区间" in prompt
    assert "不展示A/B/C中间计算细节" in prompt
    assert "next_year_eps_forecast" in prompt
    assert "next_quarter_eps_forecast × 4" in prompt


def test_earnings_commentary_is_professional_and_not_template():
    stock = {
        "symbol": "AMD",
        "financial": {
            "latest_period": "2025-12-31",
            "latest_period_type": "quarterly",
            "revenue_b": 10.27,
            "revenue_yoy_pct": 34.11,
            "net_income_b": 1.51,
            "net_income_yoy_pct": 213.49,
            "eps": 0.93,
            "gross_margin_pct": 54.30,
            "operating_margin_pct": 17.06,
            "net_margin_pct": 14.71,
        },
        "realtime": {"pe_ttm": 42.2},
        "forecast": {
            "forward_pe": 33.4,
            "peg": 1.4,
            "eps_forecast": 4.1,
            "next_quarter_eps_forecast": 1.1,
            "next_earnings_date": "2026-04-30",
        },
        "expectation_guidance": {
            "beat_miss": {
                "latest_quarter": "2025-12-31",
                "latest_eps_actual": 0.96,
                "latest_eps_estimate": 0.89,
                "latest_surprise_pct": 7.87,
                "latest_result": "beat",
            }
        },
        "ai_financial_context": {
            "annual": [
                {
                    "period_end": "2025-12-31",
                    "revenue_b": 40.8,
                    "net_income_b": 6.6,
                    "net_margin_pct": 16.2,
                    "gross_margin_pct": 55.0,
                    "shareholders_equity_b": 24.0,
                },
                {
                    "period_end": "2024-12-31",
                    "revenue_b": 31.2,
                    "net_income_b": 4.5,
                    "net_margin_pct": 14.4,
                    "gross_margin_pct": 52.1,
                    "shareholders_equity_b": 22.5,
                },
                {
                    "period_end": "2023-12-31",
                    "revenue_b": 22.7,
                    "net_income_b": 2.9,
                    "net_margin_pct": 12.8,
                    "gross_margin_pct": 49.2,
                    "shareholders_equity_b": 20.4,
                },
            ],
            "quarterly": [
                {
                    "period_end": "2025-12-31",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 4,
                    "revenue_b": 10.27,
                    "gross_margin_pct": 54.30,
                    "operating_margin_pct": 17.06,
                    "net_income_b": 1.51,
                    "net_margin_pct": 14.71,
                    "operating_cash_flow_b": 1.95,
                    "free_cash_flow_b": 1.63,
                },
                {
                    "period_end": "2025-09-30",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 3,
                    "revenue_b": 7.66,
                    "gross_margin_pct": 50.5,
                    "operating_margin_pct": 11.2,
                    "net_income_b": 0.48,
                    "net_margin_pct": 6.27,
                    "operating_cash_flow_b": 1.20,
                    "free_cash_flow_b": 0.95,
                },
                {
                    "period_end": "2024-12-31",
                    "fiscal_year": 2024,
                    "fiscal_quarter": 4,
                    "revenue_b": 7.66,
                    "gross_margin_pct": 47.9,
                    "operating_margin_pct": 10.8,
                    "net_income_b": 0.48,
                    "net_margin_pct": 6.27,
                    "operating_cash_flow_b": 1.05,
                    "free_cash_flow_b": 0.72,
                },
            ],
        },
    }

    text = stock_service._build_earnings_focus_commentary(stock)
    assert "近3年财务（商业模式竞争力 / 3Y）" in text
    assert "ROE" in text
    assert "近4季度财务（中短期经营态势 / 4Q）" in text
    assert "最新财报与下季度财报预测（预期修正/超预期判断）" in text
    assert "财报超预期" in text
    assert "下季度EPS预测" in text
    assert "总体结论" in text
    assert "3-6个月" not in text
    assert "YoY" not in text
    assert "QoQ" not in text
    assert text.count("%") <= 9


def test_financial_analysis_prompt_requires_latest_report_and_next_quarter_review():
    stocks = [
        {
            "symbol": "NVDA",
            "financial": {"latest_period": "2025-10-31", "latest_period_type": "quarterly"},
            "forecast": {"next_quarter_eps_forecast": 1.95, "next_earnings_date": "2026-02-20"},
            "expectation_guidance": {
                "beat_miss": {
                    "latest_quarter": "2025-10-31",
                    "latest_eps_actual": 0.89,
                    "latest_eps_estimate": 0.82,
                    "latest_surprise_pct": 8.54,
                    "latest_result": "beat",
                }
            },
            "ai_financial_context": {"annual": [], "quarterly": []},
            "news": [],
        }
    ]

    prompt = stock_service._build_financial_analysis_prompt(["NVDA"], stocks)

    assert "3) 点评最新财报与下季度财报预测" in prompt
    assert "预期修正与财报评价（最新财报+下季度预测）" in prompt
    assert "- 最新财报与下季度财报预测（预期修正/超预期判断）:" in prompt
    assert "- 总体结论:" in prompt


def test_normalize_ui_language_defaults_to_zh():
    assert stock_service._normalize_ui_language(None) == "zh"
    assert stock_service._normalize_ui_language("") == "zh"
    assert stock_service._normalize_ui_language("en") == "en"
    assert stock_service._normalize_ui_language("EN-us") == "en"
    assert stock_service._normalize_ui_language("zh-CN") == "zh"
    assert stock_service._normalize_ui_language("fr") == "zh"


def test_build_ai_prompt_can_output_english():
    stocks = [
        {
            "symbol": "NVDA",
            "realtime": {"change_pct": 1.2, "change_5d_pct": 2.1, "change_20d_pct": 5.1, "change_250d_pct": 88.0, "pe_ttm": 45.2},
            "forecast": {"forward_pe": 34.1, "peg": 1.9, "next_quarter_eps_forecast": 0.68, "next_earnings_date": "2026-02-26"},
            "news": [],
            "ai_financial_context": {"annual": [], "quarterly": []},
        }
    ]

    prompt = stock_service._build_ai_prompt(["NVDA"], stocks, language="en")

    assert "Output must be English Markdown" in prompt
    assert "Core conclusion" in prompt
    assert "## References" in prompt


def test_build_financial_followup_prompt_can_output_english():
    stocks = [
        {
            "symbol": "NVDA",
            "financial": {"latest_period": "2025-12-31"},
            "forecast": {"next_earnings_date": "2026-02-26"},
            "ai_financial_context": {"annual": [], "quarterly": []},
            "news": [],
        }
    ]

    prompt = stock_service._build_financial_followup_prompt(
        symbols=["NVDA"],
        stocks=stocks,
        base_analysis="Initial financial analysis",
        history=[{"role": "user", "content": "Focus on margin first"}],
        question="How large is AI revenue mix?",
        language="en",
    )

    assert "Initial financial analysis" in prompt
    assert "Latest question: How large is AI revenue mix?" in prompt
    assert "Output in English Markdown" in prompt


def test_call_openai_compatible_once_uses_english_system_prompt(monkeypatch):
    captured = {}

    class DummyResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        return DummyResp()

    monkeypatch.setattr(stock_service.requests, "post", fake_post, raising=False)

    text, finish_reason = stock_service._call_openai_compatible_once(
        prompt="test prompt",
        api_key="k",
        model="m",
        base_url="https://api.openai.com/v1",
        language="en",
    )

    system_text = captured["payload"]["messages"][0]["content"]
    assert text == "ok"
    assert finish_reason == "stop"
    assert "Respond in English" in system_text


def test_normalize_followup_history_filters_invalid_messages():
    out = stock_service._normalize_followup_history(
        [
            {"role": "user", "content": "  问题1  "},
            {"role": "assistant", "content": "回答1"},
            {"role": "system", "content": "ignore"},
            {"role": "user", "content": "   "},
            "not-a-dict",
            {"role": "ASSISTANT", "content": "回答2"},
        ],
        max_messages=10,
    )

    assert out == [
        {"role": "user", "content": "问题1"},
        {"role": "assistant", "content": "回答1"},
        {"role": "assistant", "content": "回答2"},
    ]


def test_normalize_followup_history_keeps_full_history_by_default():
    history = []
    for i in range(15):
        role = "user" if i % 2 == 0 else "assistant"
        history.append({"role": role, "content": f"msg-{i}"})

    long_text = "A" * 5000
    history.append({"role": "user", "content": long_text})

    out = stock_service._normalize_followup_history(history)

    assert len(out) == 16
    assert out[-1]["content"] == long_text


def test_build_financial_followup_prompt_includes_base_and_history():
    stocks = [
        {
            "symbol": "NVDA",
            "financial": {"latest_period": "2025-12-31"},
            "forecast": {"next_earnings_date": "2026-02-26"},
            "ai_financial_context": {"annual": [], "quarterly": []},
            "news": [],
        }
    ]

    prompt = stock_service._build_financial_followup_prompt(
        symbols=["NVDA"],
        stocks=stocks,
        base_analysis="初始财务结论",
        history=[
            {"role": "user", "content": "先看毛利率"},
            {"role": "assistant", "content": "毛利率维持高位"},
        ],
        question="AI业务收入占比是多少？",
    )

    assert "初始财务结论" in prompt
    assert "用户: 先看毛利率" in prompt
    assert "助手: 毛利率维持高位" in prompt
    assert "最新追问: AI业务收入占比是多少？" in prompt


def test_generate_ai_investment_followup_auto_continues_when_truncated(monkeypatch):
    calls = []

    def fake_call(provider_key, prompt, api_key, model, base_url=None):
        calls.append(prompt)
        if len(calls) == 1:
            return "第一段", "length"
        return "第二段", "stop"

    monkeypatch.setattr(stock_service, "_call_ai_once", fake_call, raising=False)

    text = stock_service.generate_ai_investment_followup(
        symbols=["NVDA"],
        stocks=[
            {
                "symbol": "NVDA",
                "realtime": {},
                "forecast": {},
                "news": [],
                "ai_financial_context": {"annual": [], "quarterly": []},
            }
        ],
        provider="openai",
        api_key="k",
        model="m",
        base_analysis="初始建议",
        history=[{"role": "user", "content": "上一轮问题"}],
        question="AMD 最新动态？",
    )

    assert "第一段" in text
    assert "第二段" in text
    assert len(calls) == 2
    assert "继续未完成的部分" in calls[1]


def test_build_external_search_context_returns_ten_items_per_stock(monkeypatch):
    calls = {"exa": 0, "tavily": 0}

    def fake_exa(query, api_key, max_results=6, lookback_days=60):
        calls["exa"] += 1
        symbol = str(query).split(" ")[0]
        return [
            {
                "provider": "exa",
                "title": f"{symbol} news #{i}",
                "url": f"https://example.com/{symbol.lower()}/{i}",
                "published_at": "2026-02-09",
                "source": "Reuters",
                "snippet": f"{symbol} snippet {i}",
            }
            for i in range(1, 13)
        ]

    def fake_tavily(query, api_key, max_results=6, lookback_days=60):
        calls["tavily"] += 1
        return []

    monkeypatch.setattr(stock_service, "_search_with_exa", fake_exa, raising=False)
    monkeypatch.setattr(stock_service, "_search_with_tavily", fake_tavily, raising=False)

    context = stock_service._build_external_search_context(
        symbols=["NVDA", "AMD"],
        mode="financial",
        exa_api_key="exa-k",
    )

    exa_lines = [line for line in str(context).splitlines() if re.match(r"^\d+\.\s+\[EXA\]", line)]
    assert "### NVDA" in context
    assert "### AMD" in context
    assert len(exa_lines) == 20
    assert calls["exa"] == 4
    assert calls["tavily"] == 0


def test_get_stock_bundle_requests_ten_news_items(monkeypatch):
    monkeypatch.setattr(stock_service, "get_cached_financial_bundle", lambda symbol, ttl_hours=12: None, raising=False)
    monkeypatch.setattr(stock_service, "set_cached_financial_bundle", lambda symbol, financial, ctx: None, raising=False)
    monkeypatch.setattr(stock_service, "_get_realtime_from_yfinance", lambda symbol: {}, raising=False)
    monkeypatch.setattr(stock_service, "_get_financial_from_yfinance", lambda symbol: {}, raising=False)
    monkeypatch.setattr(
        stock_service,
        "_build_ai_financial_context_from_yfinance",
        lambda symbol, annual_limit=3, quarterly_limit=4: {"annual": [], "quarterly": []},
        raising=False,
    )
    monkeypatch.setattr(stock_service, "_get_forecast_from_yahoo", lambda symbol: {}, raising=False)
    monkeypatch.setattr(stock_service, "_get_prediction_fields_from_yfinance", lambda symbol: {}, raising=False)
    monkeypatch.setattr(
        stock_service,
        "_build_expectation_guidance_snapshot",
        lambda symbol, news=None, **kwargs: {"conclusion": {"overall": "ok"}},
        raising=False,
    )

    captured = {}

    def fake_recent_news(symbol, api_key, limit=5):
        captured["limit"] = limit
        return [{"title": f"n{i}", "publisher": "p", "link": f"https://example.com/{i}"} for i in range(limit)]

    monkeypatch.setattr(stock_service, "_get_recent_news", fake_recent_news, raising=False)

    bundle = stock_service.get_stock_bundle("NVDA", "finnhub-key")

    assert captured["limit"] == 10
    assert len(bundle["news"]) == 10


def test_financial_stock_context_uses_top_ten_news():
    stock = {
        "symbol": "NVDA",
        "financial": {},
        "forecast": {},
        "expectation_guidance": {"beat_miss": {}},
        "ai_financial_context": {"annual": [], "quarterly": []},
        "news": [
            {"title": f"headline-{i}", "publisher": "Reuters", "published_at": "2026-02-09"}
            for i in range(1, 13)
        ],
    }

    text = stock_service._build_financial_analysis_stock_context(stock)

    assert "headline-10" in text
    assert "headline-11" not in text
