from types import SimpleNamespace

import pandas as pd

import stock_service


def test_build_expectation_guidance_snapshot_from_search(monkeypatch):
    earnings_history = pd.DataFrame(
        {
            "epsActual": [0.89, 0.81, 1.05, 1.30],
            "epsEstimate": [0.8456, 0.7499, 1.0087, 1.2565],
            "epsDifference": [0.0444, 0.0601, 0.0413, 0.0435],
            "surprisePercent": [0.0525, 0.0802, 0.0410, 0.0346],
        },
        index=[
            pd.Timestamp("2025-01-31"),
            pd.Timestamp("2025-04-30"),
            pd.Timestamp("2025-07-31"),
            pd.Timestamp("2025-10-31"),
        ],
    )

    eps_trend = pd.DataFrame(
        {
            "current": [1.52289, 1.65303, 4.69210, 7.71393],
            "7daysAgo": [1.52289, 1.65285, 4.69210, 7.66386],
            "30daysAgo": [1.52158, 1.64721, 4.69153, 7.56654],
            "60daysAgo": [1.52083, 1.63687, 4.68543, 7.49000],
            "90daysAgo": [1.41874, 1.50314, 4.54143, 6.70493],
        },
        index=["0q", "+1q", "0y", "+1y"],
    )

    fake_ticker = SimpleNamespace(
        get_earnings_history=lambda: earnings_history,
        get_eps_trend=lambda: eps_trend,
    )
    monkeypatch.setattr(stock_service, "yf", SimpleNamespace(Ticker=lambda symbol: fake_ticker), raising=False)
    out = stock_service._build_expectation_guidance_snapshot(
        "NVDA",
        news=[
            {
                "title": "NVIDIA raises full-year revenue outlook after strong demand",
                "publisher": "Reuters",
                "link": "https://example.com/reuters-guidance-up",
            }
        ],
    )

    assert out["beat_miss"]["latest_result"] == "beat"
    assert out["beat_miss"]["beat_count_4q"] == 4
    assert out["guidance"]["signal"] == "insufficient"
    assert "已下线" in out["guidance"]["conclusion"]
    assert out["eps_trend"]["period"] == "+1y"
    assert out["eps_trend"]["change_vs_90d_pct"] > 0
    assert out["conclusion"]["overall"]


def test_build_expectation_guidance_snapshot_handles_missing_data(monkeypatch):
    monkeypatch.setattr(stock_service, "yf", None, raising=False)

    out = stock_service._build_expectation_guidance_snapshot("NVDA", news=[])

    assert out["beat_miss"]["latest_result"] == "insufficient"
    assert out["guidance"]["signal"] == "insufficient"
    assert out["eps_trend"]["period"] is None
    assert "信息不足" in out["conclusion"]["overall"]


def test_get_stock_bundle_includes_expectation_guidance(monkeypatch):
    monkeypatch.setattr(
        stock_service,
        "get_cached_financial_bundle",
        lambda symbol, ttl_hours=12: None,
        raising=False,
    )
    monkeypatch.setattr(stock_service, "set_cached_financial_bundle", lambda symbol, financial, ctx: None, raising=False)
    monkeypatch.setattr(
        stock_service,
        "_get_realtime_from_yfinance",
        lambda symbol: {
            "price": 100,
            "change_pct": 0.5,
            "market_cap_b": 1000,
            "turnover_b": 10,
            "pe_ttm": 30,
            "change_5d_pct": 1,
            "change_20d_pct": 2,
            "change_250d_pct": 3,
        },
        raising=False,
    )
    monkeypatch.setattr(stock_service, "_get_financial_from_yfinance", lambda symbol: {"latest_period": "2025-10-31"}, raising=False)
    monkeypatch.setattr(
        stock_service,
        "_build_ai_financial_context_from_yfinance",
        lambda symbol, annual_limit=3, quarterly_limit=4: {"annual": [], "quarterly": []},
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_get_forecast_from_yahoo",
        lambda symbol: {"forward_pe": 28.8},
        raising=False,
    )
    monkeypatch.setattr(
        stock_service,
        "_get_prediction_fields_from_yfinance",
        lambda symbol: {
            "eps_forecast": 4.1,
            "next_year_eps_forecast": 4.8,
            "next_quarter_eps_forecast": 1.05,
            "next_earnings_date": "2026-03-01",
        },
        raising=False,
    )
    monkeypatch.setattr(stock_service, "_get_recent_news", lambda symbol, api_key, limit=5: [], raising=False)
    monkeypatch.setattr(
        stock_service,
        "_build_expectation_guidance_snapshot",
        lambda symbol, news=None, **kwargs: {"conclusion": {"overall": "ok"}},
        raising=False,
    )

    bundle = stock_service.get_stock_bundle("NVDA", "")

    assert "expectation_guidance" in bundle
    assert bundle["expectation_guidance"]["conclusion"]["overall"] == "ok"
