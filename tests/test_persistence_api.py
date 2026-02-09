from io import BytesIO

import pandas as pd

import app


def test_watchlist_api_roundtrip(monkeypatch):
    monkeypatch.setattr(
        app,
        "create_watchlist_entry",
        lambda name, symbols: 7,
    )
    monkeypatch.setattr(
        app,
        "list_watchlist_entries",
        lambda limit=200: [
            {
                "id": 7,
                "name": "core holdings",
                "symbols": ["NVDA", "AMD"],
                "updated_at": "2026-02-08T00:00:00+00:00",
                "created_at": "2026-02-08T00:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        app,
        "get_watchlist_entry",
        lambda watchlist_id: {
            "id": int(watchlist_id),
            "name": "core holdings",
            "symbols": ["NVDA", "AMD"],
            "updated_at": "2026-02-08T00:00:00+00:00",
            "created_at": "2026-02-08T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        app,
        "update_watchlist_entry_name",
        lambda watchlist_id, name: {
            "id": int(watchlist_id),
            "name": str(name),
            "symbols": ["NVDA", "AMD"],
            "updated_at": "2026-02-08T01:00:00+00:00",
            "created_at": "2026-02-08T00:00:00+00:00",
        },
    )

    client = app.app.test_client()
    save_resp = client.post("/api/watchlist", json={"name": "core holdings", "symbols": ["nvda", "amd"]})
    get_resp = client.get("/api/watchlist")
    detail_resp = client.get("/api/watchlist/7")
    rename_resp = client.patch("/api/watchlist/7", json={"name": "semiconductor watch"})

    assert save_resp.status_code == 200
    assert save_resp.get_json()["id"] == 7
    assert get_resp.status_code == 200
    assert get_resp.get_json()["items"][0]["symbols"] == ["NVDA", "AMD"]
    assert detail_resp.status_code == 200
    assert detail_resp.get_json()["id"] == 7
    assert rename_resp.status_code == 200
    assert rename_resp.get_json()["name"] == "semiconductor watch"


def test_watchlist_rename_requires_name():
    client = app.app.test_client()
    resp = client.patch("/api/watchlist/7", json={"name": "  "})

    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_watchlist_rename_not_found(monkeypatch):
    monkeypatch.setattr(app, "update_watchlist_entry_name", lambda watchlist_id, name: None)
    client = app.app.test_client()

    resp = client.patch("/api/watchlist/999", json={"name": "missing"})

    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_ai_history_routes_removed():
    client = app.app.test_client()

    list_resp = client.get("/api/ai-history")
    detail_resp = client.get("/api/ai-history/123")
    delete_resp = client.delete("/api/ai-history/123")

    assert list_resp.status_code == 404
    assert detail_resp.status_code == 404
    assert delete_resp.status_code == 404


def test_ai_analysis_no_history_id(monkeypatch):
    monkeypatch.setattr(app, "generate_ai_investment_advice", lambda **kwargs: "analysis result")

    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis",
        json={
            "symbols": ["NVDA"],
            "stocks": [
                {
                    "symbol": "NVDA",
                    "ai_financial_context": {"annual": [{"period_end": "2025-12-31"}], "quarterly": [{"period_end": "2025-09-30"}]},
                }
            ],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
        },
    )

    assert resp.status_code == 200
    assert "history_id" not in resp.get_json()


def test_compare_allows_empty_finnhub_key(monkeypatch):
    calls = {}

    def fake_fetch(symbols, finnhub_api_key, force_refresh_financial=False):
        calls["symbols"] = symbols
        calls["finnhub_api_key"] = finnhub_api_key
        calls["force_refresh_financial"] = force_refresh_financial
        return [{"symbol": "NVDA", "realtime": {}, "financial": {}, "forecast": {}, "news": []}]

    monkeypatch.setattr(app, "fetch_multiple_stocks", fake_fetch)

    client = app.app.test_client()
    resp = client.get("/api/compare?symbols=NVDA")

    assert resp.status_code == 200
    assert calls["symbols"] == ["NVDA"]
    assert calls["finnhub_api_key"] == ""
    assert calls["force_refresh_financial"] is False


def test_export_excel_allows_empty_finnhub_key(monkeypatch):
    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [],
    )
    monkeypatch.setattr(app, "_build_excel_file", lambda stocks, symbols: BytesIO(b"fake-xlsx"))

    client = app.app.test_client()
    resp = client.post("/api/export-excel", json={"symbols": ["NVDA"]})

    assert resp.status_code == 200
    assert resp.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_export_excel_has_separate_prediction_and_valuation_sheets():
    stream = app._build_excel_file(
        stocks=[
            {
                "symbol": "NVDA",
                "realtime": {},
                "financial": {},
                "forecast": {
                    "forward_pe": 32.8,
                    "peg": 1.62,
                    "eps_forecast": 4.2,
                    "next_year_eps_forecast": 5.4,
                    "next_quarter_eps_forecast": 1.1,
                    "ev_to_ebitda": 20.5,
                    "ps": 12.3,
                    "next_earnings_date": "2026-03-01",
                },
                "news": [],
            }
        ],
        symbols=["NVDA"],
    )

    xls = pd.ExcelFile(stream)
    assert "prediction" in xls.sheet_names
    assert "valuation" in xls.sheet_names

    prediction_df = pd.read_excel(stream, sheet_name="prediction")
    stream.seek(0)
    valuation_df = pd.read_excel(stream, sheet_name="valuation")

    assert "预测EPS(Next Year)" in prediction_df.columns
    assert float(prediction_df.loc[0, "预测EPS(Next Year)"]) == 5.4

    assert "EV/EBITDA" in valuation_df.columns
    assert "P/S (TTM)" in valuation_df.columns
    assert float(valuation_df.loc[0, "EV/EBITDA"]) == 20.5
    assert float(valuation_df.loc[0, "P/S (TTM)"]) == 12.3

    cols = list(prediction_df.columns)
    assert cols.index("预测EPS(USD/股)") < cols.index("预测EPS(Next Year)") < cols.index("下季度预测EPS(USD/股)")


def test_ai_analysis_fetches_stocks_without_finnhub_key(monkeypatch):
    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {
                "symbol": "NVDA",
                "ai_financial_context": {
                    "annual": [{"period_end": "2025-12-31"}],
                    "quarterly": [{"period_end": "2025-09-30"}],
                },
            }
        ],
    )
    monkeypatch.setattr(app, "generate_ai_investment_advice", lambda **kwargs: "analysis result")

    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis",
        json={
            "symbols": ["NVDA"],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["analysis"] == "analysis result"


def test_ai_analysis_passes_search_api_keys(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {
                "symbol": "NVDA",
                "ai_financial_context": {
                    "annual": [{"period_end": "2025-12-31"}],
                    "quarterly": [{"period_end": "2025-09-30"}],
                },
            }
        ],
    )

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "analysis result"

    monkeypatch.setattr(app, "generate_ai_investment_advice", fake_generate, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis",
        json={
            "symbols": ["NVDA"],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "exa_api_key": "exa-k",
            "tavily_api_key": "tavily-k",
        },
    )

    assert resp.status_code == 200
    assert captured["exa_api_key"] == "exa-k"
    assert captured["tavily_api_key"] == "tavily-k"


def test_ai_analysis_uses_search_api_keys_from_env(monkeypatch):
    captured = {}

    monkeypatch.setenv("EXA_API_KEY", "exa-env")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-env")
    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {
                "symbol": "NVDA",
                "ai_financial_context": {
                    "annual": [{"period_end": "2025-12-31"}],
                    "quarterly": [{"period_end": "2025-09-30"}],
                },
            }
        ],
    )

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "analysis result"

    monkeypatch.setattr(app, "generate_ai_investment_advice", fake_generate, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis",
        json={
            "symbols": ["NVDA"],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
        },
    )

    assert resp.status_code == 200
    assert captured["exa_api_key"] == "exa-env"
    assert captured["tavily_api_key"] == "tavily-env"


def test_financial_analysis_fetches_stocks_without_finnhub_key(monkeypatch):
    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {"symbol": "NVDA", "realtime": {}, "financial": {}, "forecast": {}, "news": []}
        ],
    )
    monkeypatch.setattr(app, "generate_financial_analysis", lambda **kwargs: "financial analysis")

    client = app.app.test_client()
    resp = client.post(
        "/api/financial-analysis",
        json={
            "symbols": ["NVDA"],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["analysis"] == "financial analysis"


def test_financial_analysis_passes_search_api_keys(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {"symbol": "NVDA", "realtime": {}, "financial": {}, "forecast": {}, "news": []}
        ],
    )

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "financial analysis"

    monkeypatch.setattr(app, "generate_financial_analysis", fake_generate, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/financial-analysis",
        json={
            "symbols": ["NVDA"],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "exa_api_key": "exa-k",
            "tavily_api_key": "tavily-k",
        },
    )

    assert resp.status_code == 200
    assert captured["exa_api_key"] == "exa-k"
    assert captured["tavily_api_key"] == "tavily-k"


def test_financial_analysis_uses_search_api_keys_from_env(monkeypatch):
    captured = {}

    monkeypatch.setenv("EXA_API_KEY", "exa-env")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-env")
    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {"symbol": "NVDA", "realtime": {}, "financial": {}, "forecast": {}, "news": []}
        ],
    )

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "financial analysis"

    monkeypatch.setattr(app, "generate_financial_analysis", fake_generate, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/financial-analysis",
        json={
            "symbols": ["NVDA"],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
        },
    )

    assert resp.status_code == 200
    assert captured["exa_api_key"] == "exa-env"
    assert captured["tavily_api_key"] == "tavily-env"


def test_target_price_analysis_passes_search_api_keys(monkeypatch):
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "target price analysis"

    monkeypatch.setattr(app, "generate_target_price_analysis", fake_generate, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/target-price-analysis",
        json={
            "symbols": ["NVDA"],
            "stocks": [
                {
                    "symbol": "NVDA",
                    "realtime": {},
                    "forecast": {},
                    "news": [],
                    "ai_financial_context": {"annual": [{"period_end": "2025-12-31"}], "quarterly": [{"period_end": "2025-09-30"}]},
                }
            ],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "exa_api_key": "exa-k",
            "tavily_api_key": "tavily-k",
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["analysis"] == "target price analysis"
    assert captured["exa_api_key"] == "exa-k"
    assert captured["tavily_api_key"] == "tavily-k"


def test_financial_analysis_followup_passes_history(monkeypatch):
    captured = {}

    def fake_followup(**kwargs):
        captured.update(kwargs)
        return "followup answer"

    monkeypatch.setattr(app, "generate_financial_analysis_followup", fake_followup, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/financial-analysis-followup",
        json={
            "symbols": ["NVDA"],
            "stocks": [{"symbol": "NVDA", "financial": {}, "forecast": {}, "news": []}],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "base_analysis": "initial analysis",
            "history": [{"role": "user", "content": "check margin first"}],
            "question": "what is ai revenue mix?",
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["answer"] == "followup answer"
    assert captured["question"] == "what is ai revenue mix?"
    assert captured["history"] == [{"role": "user", "content": "check margin first"}]


def test_ai_analysis_followup_fetches_stocks_without_finnhub_key(monkeypatch):
    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {
                "symbol": "NVDA",
                "realtime": {},
                "forecast": {},
                "news": [],
                "ai_financial_context": {"annual": [], "quarterly": []},
            }
        ],
    )
    monkeypatch.setattr(app, "generate_ai_investment_followup", lambda **kwargs: "ai followup", raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis-followup",
        json={
            "symbols": ["NVDA"],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "history": [{"role": "assistant", "content": "initial suggestion"}],
            "question": "AMD latest update?",
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["answer"] == "ai followup"


def test_ai_analysis_followup_requires_question():
    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis-followup",
        json={
            "symbols": ["NVDA"],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
        },
    )

    assert resp.status_code == 400
    assert "追问内容不能为空" in resp.get_json()["error"]

def test_test_config_supports_exa_target(monkeypatch):
    monkeypatch.setattr(app, "test_exa_api_key", lambda api_key: (True, "Exa ok"), raising=False)
    client = app.app.test_client()

    resp = client.post(
        "/api/test-config",
        json={
            "target": "exa",
            "exa_api_key": "exa-k",
        },
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "Exa" in data["message"]


def test_test_config_supports_tavily_target(monkeypatch):
    monkeypatch.setattr(app, "test_tavily_api_key", lambda api_key: (True, "Tavily ok"), raising=False)
    client = app.app.test_client()

    resp = client.post(
        "/api/test-config",
        json={
            "target": "tavily",
            "tavily_api_key": "tv-k",
        },
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "Tavily" in data["message"]


def test_test_config_uses_exa_key_from_env(monkeypatch):
    captured = {}

    def fake_test(api_key):
        captured["api_key"] = api_key
        return True, "ok"

    monkeypatch.setenv("EXA_API_KEY", "exa-env")
    monkeypatch.setattr(app, "test_exa_api_key", fake_test, raising=False)
    client = app.app.test_client()

    resp = client.post("/api/test-config", json={"target": "exa"})

    assert resp.status_code == 200
    assert captured["api_key"] == "exa-env"


def test_test_config_uses_tavily_key_from_env(monkeypatch):
    captured = {}

    def fake_test(api_key):
        captured["api_key"] = api_key
        return True, "ok"

    monkeypatch.setenv("TAVILY_API_KEY", "tavily-env")
    monkeypatch.setattr(app, "test_tavily_api_key", fake_test, raising=False)
    client = app.app.test_client()

    resp = client.post("/api/test-config", json={"target": "tavily"})

    assert resp.status_code == 200
    assert captured["api_key"] == "tavily-env"


def test_build_analysis_request_context_reads_payload_and_env(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-env")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-env")

    ctx = app._build_analysis_request_context(
        {
            "symbols": ["nvda", "amd"],
            "finnhub_api_key": "fin",
            "provider": "openai",
            "api_key": "k",
            "model": "m",
        }
    )

    assert ctx["symbols"] == ["NVDA", "AMD"]
    assert ctx["finnhub_api_key"] == "fin"
    assert ctx["provider"] == "openai"
    assert ctx["api_key"] == "k"
    assert ctx["model"] == "m"
    assert ctx["exa_api_key"] == "exa-env"
    assert ctx["tavily_api_key"] == "tavily-env"


def test_resolve_analysis_stocks_refetches_when_ai_context_missing(monkeypatch):
    calls = {"count": 0}

    def fake_fetch(
        symbols,
        finnhub_api_key,
        force_refresh_financial=False,
        exa_api_key=None,
        tavily_api_key=None,
        ai_provider=None,
        ai_api_key=None,
        ai_model=None,
        ai_base_url=None,
    ):
        calls["count"] += 1
        return [
            {
                "symbol": "NVDA",
                "ai_financial_context": {
                    "annual": [{"period_end": "2025-12-31"}],
                    "quarterly": [{"period_end": "2025-09-30"}],
                },
            }
        ]

    monkeypatch.setattr(app, "_fetch_multiple_stocks_compat", fake_fetch, raising=False)

    context = app._build_analysis_request_context(
        {
            "symbols": ["NVDA"],
            "finnhub_api_key": "",
            "provider": "openai",
            "api_key": "k",
            "model": "m",
        }
    )
    out = app._resolve_analysis_stocks(
        context=context,
        stocks=[
            {
                "symbol": "NVDA",
                "ai_financial_context": {"annual": [], "quarterly": []},
            }
        ],
        require_ai_context=True,
    )

    assert calls["count"] == 1
    assert out[0]["symbol"] == "NVDA"
