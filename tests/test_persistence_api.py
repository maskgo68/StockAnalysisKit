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


def test_watchlist_api_accepts_global_numeric_symbols():
    client = app.app.test_client()

    resp = client.post(
        "/api/watchlist",
        json={"name": "global", "symbols": ["0700.HK", "600519.SS"]},
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["symbols"] == ["0700.HK", "600519.SS"]


def test_investment_note_api_accepts_global_numeric_symbol():
    client = app.app.test_client()

    create_resp = client.post(
        "/api/investment-notes",
        json={"symbol": "0700.HK", "content": "跟踪腾讯广告业务恢复节奏"},
    )
    list_resp = client.get("/api/investment-notes?symbol=0700.HK")

    assert create_resp.status_code == 200
    assert list_resp.status_code == 200
    items = list_resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["symbol"] == "0700.HK"


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


def test_compare_returns_partial_error_list_when_some_symbols_fail(monkeypatch):
    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {
                "symbol": "NVDA",
                "realtime": {"price": 120.0},
                "financial": {},
                "forecast": {},
                "news": [],
            },
            {
                "symbol": "AMD",
                "error": "抓取失败: TimeoutError: upstream timeout",
                "realtime": {},
                "financial": {},
                "forecast": {},
                "news": [],
            },
        ],
    )

    client = app.app.test_client()
    resp = client.get("/api/compare?symbols=NVDA,AMD")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["symbols"] == ["NVDA", "AMD"]
    assert isinstance(data.get("errors"), list)
    assert len(data["errors"]) == 1
    assert data["errors"][0]["symbol"] == "AMD"
    assert "TimeoutError" in data["errors"][0]["error"]


def test_compare_returns_502_when_all_symbols_fail(monkeypatch):
    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {
                "symbol": "NVDA",
                "error": "抓取失败: ConnectionError: name resolution failed",
                "realtime": {},
                "financial": {},
                "forecast": {},
                "news": [],
            }
        ],
    )

    client = app.app.test_client()
    resp = client.get("/api/compare?symbols=NVDA")

    assert resp.status_code == 502
    data = resp.get_json()
    assert data["code"] == "ALL_SYMBOLS_FETCH_FAILED"
    assert data["ok"] is False
    assert isinstance(data.get("details"), dict)
    assert isinstance(data["details"].get("errors"), list)
    assert data["details"]["errors"][0]["symbol"] == "NVDA"


def test_compare_includes_warning_details_for_partial_source_failures(monkeypatch):
    monkeypatch.setattr(
        app,
        "fetch_multiple_stocks",
        lambda symbols, finnhub_api_key, force_refresh_financial=False: [
            {
                "symbol": "NVDA",
                "realtime": {"price": 120.0},
                "financial": {},
                "forecast": {},
                "news": [],
                "warnings": [
                    {
                        "source": "yahoo.quote_summary",
                        "message": "HTTP 429 - Too Many Requests",
                        "status_code": 429,
                    }
                ],
            }
        ],
    )

    client = app.app.test_client()
    resp = client.get("/api/compare?symbols=NVDA")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data.get("warnings"), list)
    assert data["warnings"][0]["symbol"] == "NVDA"
    assert "429" in data["warnings"][0]["error"]


def test_unhandled_api_exception_returns_json_error(monkeypatch):
    def _raise_unexpected(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(app, "generate_ai_investment_advice", _raise_unexpected, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis",
        json={
            "symbols": ["NVDA"],
            "stocks": [
                {
                    "symbol": "NVDA",
                    "ai_financial_context": {
                        "annual": [{"period_end": "2025-12-31"}],
                        "quarterly": [{"period_end": "2025-09-30"}],
                    },
                }
            ],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
        },
    )

    assert resp.status_code == 500
    data = resp.get_json()
    assert data["ok"] is False
    assert data["code"] == "INTERNAL_SERVER_ERROR"
    assert isinstance(data.get("request_id"), str)
    assert data["request_id"]


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
    stream.seek(0)
    realtime_df = pd.read_excel(stream, sheet_name="realtime")

    assert "预测EPS(Next Year, 本币/股)" in prediction_df.columns
    assert float(prediction_df.loc[0, "预测EPS(Next Year, 本币/股)"]) == 5.4

    assert "EV/EBITDA" in valuation_df.columns
    assert "P/S (TTM)" in valuation_df.columns
    assert float(valuation_df.loc[0, "EV/EBITDA"]) == 20.5
    assert float(valuation_df.loc[0, "P/S (TTM)"]) == 12.3

    assert "股票名称" in realtime_df.columns
    assert "交易日期" in realtime_df.columns

    cols = list(prediction_df.columns)
    assert cols.index("预测币种") < cols.index("预测EPS(Current Year, 本币/股)") < cols.index("预测EPS(Next Year, 本币/股)") < cols.index("预测EPS(Next Quarter, 本币/股)")


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


def test_ai_analysis_returns_error_model_when_api_key_missing():
    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis",
        json={
            "symbols": ["NVDA"],
            "stocks": [
                {
                    "symbol": "NVDA",
                    "realtime": {},
                    "forecast": {},
                    "news": [],
                    "ai_financial_context": {
                        "annual": [{"period_end": "2025-12-31"}],
                        "quarterly": [{"period_end": "2025-09-30"}],
                    },
                }
            ],
            "provider": "openai",
            "api_key": "",
            "model": "m",
        },
    )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "AI_API_KEY_MISSING"
    assert data["message"]
    assert data["error"] == data["message"]


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


def test_target_price_analysis_returns_error_model_when_model_missing():
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
                    "ai_financial_context": {
                        "annual": [{"period_end": "2025-12-31"}],
                        "quarterly": [{"period_end": "2025-09-30"}],
                    },
                }
            ],
            "provider": "openai",
            "api_key": "k",
            "model": "",
        },
    )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "AI_MODEL_MISSING"
    assert data["message"]
    assert data["error"] == data["message"]


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


def test_ai_analysis_followup_returns_error_model_when_api_key_missing():
    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis-followup",
        json={
            "symbols": ["NVDA"],
            "stocks": [
                {
                    "symbol": "NVDA",
                    "realtime": {},
                    "forecast": {},
                    "news": [],
                    "ai_financial_context": {
                        "annual": [{"period_end": "2025-12-31"}],
                        "quarterly": [{"period_end": "2025-09-30"}],
                    },
                }
            ],
            "provider": "openai",
            "api_key": "",
            "model": "m",
            "base_analysis": "base",
            "history": [{"role": "assistant", "content": "a1"}],
            "question": "q2",
        },
    )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "AI_API_KEY_MISSING"
    assert data["message"]
    assert data["error"] == data["message"]


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


def test_build_analysis_request_context_normalizes_language():
    zh_ctx = app._build_analysis_request_context({"symbols": ["nvda"]})
    en_ctx = app._build_analysis_request_context({"symbols": ["nvda"], "language": "EN-us"})
    invalid_ctx = app._build_analysis_request_context({"symbols": ["nvda"], "language": "es"})

    assert zh_ctx["language"] == "zh"
    assert en_ctx["language"] == "en"
    assert invalid_ctx["language"] == "zh"


def test_ai_analysis_passes_language_to_generator(monkeypatch):
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "analysis result"

    monkeypatch.setattr(app, "generate_ai_investment_advice", fake_generate, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis",
        json={
            "symbols": ["NVDA"],
            "stocks": [
                {
                    "symbol": "NVDA",
                    "realtime": {},
                    "forecast": {},
                    "news": [],
                    "ai_financial_context": {
                        "annual": [{"period_end": "2025-12-31"}],
                        "quarterly": [{"period_end": "2025-09-30"}],
                    },
                }
            ],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "language": "en",
        },
    )

    assert resp.status_code == 200
    assert captured["language"] == "en"


def test_financial_analysis_passes_language_to_generator(monkeypatch):
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "financial analysis"

    monkeypatch.setattr(app, "generate_financial_analysis", fake_generate, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/financial-analysis",
        json={
            "symbols": ["NVDA"],
            "stocks": [{"symbol": "NVDA", "realtime": {}, "financial": {}, "forecast": {}, "news": []}],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "language": "en",
        },
    )

    assert resp.status_code == 200
    assert captured["language"] == "en"


def test_target_price_analysis_passes_language_to_generator(monkeypatch):
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "target analysis"

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
                    "ai_financial_context": {
                        "annual": [{"period_end": "2025-12-31"}],
                        "quarterly": [{"period_end": "2025-09-30"}],
                    },
                }
            ],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "language": "en",
        },
    )

    assert resp.status_code == 200
    assert captured["language"] == "en"


def test_followup_routes_pass_language_to_generator(monkeypatch):
    financial_captured = {}
    ai_captured = {}

    def fake_financial_followup(**kwargs):
        financial_captured.update(kwargs)
        return "financial followup answer"

    def fake_ai_followup(**kwargs):
        ai_captured.update(kwargs)
        return "ai followup answer"

    monkeypatch.setattr(app, "generate_financial_analysis_followup", fake_financial_followup, raising=False)
    monkeypatch.setattr(app, "generate_ai_investment_followup", fake_ai_followup, raising=False)

    client = app.app.test_client()

    financial_resp = client.post(
        "/api/financial-analysis-followup",
        json={
            "symbols": ["NVDA"],
            "stocks": [{"symbol": "NVDA", "financial": {}, "forecast": {}, "news": []}],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "language": "en",
            "base_analysis": "base",
            "history": [{"role": "user", "content": "q1"}],
            "question": "q2",
        },
    )
    ai_resp = client.post(
        "/api/ai-analysis-followup",
        json={
            "symbols": ["NVDA"],
            "stocks": [
                {
                    "symbol": "NVDA",
                    "realtime": {},
                    "forecast": {},
                    "news": [],
                    "ai_financial_context": {
                        "annual": [{"period_end": "2025-12-31"}],
                        "quarterly": [{"period_end": "2025-09-30"}],
                    },
                }
            ],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "language": "en",
            "base_analysis": "base",
            "history": [{"role": "assistant", "content": "a1"}],
            "question": "q2",
        },
    )

    assert financial_resp.status_code == 200
    assert ai_resp.status_code == 200
    assert financial_captured["language"] == "en"
    assert ai_captured["language"] == "en"


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

    monkeypatch.setattr(app, "fetch_multiple_stocks", fake_fetch, raising=False)

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


def test_ai_analysis_persists_history(monkeypatch):
    captured = {}

    monkeypatch.setattr(app, "generate_ai_investment_advice", lambda **kwargs: "analysis result", raising=False)

    def fake_create_history(**kwargs):
        captured.update(kwargs)
        return 123

    monkeypatch.setattr(app, "create_analysis_history_entry", fake_create_history, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/ai-analysis",
        json={
            "symbols": ["NVDA", "AMD"],
            "stocks": [
                {
                    "symbol": "NVDA",
                    "ai_financial_context": {
                        "annual": [{"period_end": "2025-12-31"}],
                        "quarterly": [{"period_end": "2025-09-30"}],
                    },
                },
                {
                    "symbol": "AMD",
                    "ai_financial_context": {
                        "annual": [{"period_end": "2025-12-31"}],
                        "quarterly": [{"period_end": "2025-09-30"}],
                    },
                },
            ],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "language": "en",
        },
    )

    assert resp.status_code == 200
    assert captured["symbols"] == ["NVDA", "AMD"]
    assert captured["analysis_type"] == "ai"
    assert captured["analysis"] == "analysis result"
    assert captured["provider"] == "openai"
    assert captured["model"] == "m"
    assert captured["language"] == "en"


def test_financial_analysis_persists_history(monkeypatch):
    captured = {}

    monkeypatch.setattr(app, "generate_financial_analysis", lambda **kwargs: "financial result", raising=False)

    def fake_create_history(**kwargs):
        captured.update(kwargs)
        return 456

    monkeypatch.setattr(app, "create_analysis_history_entry", fake_create_history, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/financial-analysis",
        json={
            "symbols": ["NVDA"],
            "stocks": [{"symbol": "NVDA", "realtime": {}, "financial": {}, "forecast": {}, "news": []}],
            "provider": "openai",
            "api_key": "k",
            "model": "m",
            "language": "zh",
        },
    )

    assert resp.status_code == 200
    assert captured["symbols"] == ["NVDA"]
    assert captured["analysis_type"] == "financial"
    assert captured["analysis"] == "financial result"
    assert captured["provider"] == "openai"
    assert captured["model"] == "m"
    assert captured["language"] == "zh"


def test_financial_analysis_does_not_persist_history_without_ai_config(monkeypatch):
    called = {"value": False}

    monkeypatch.setattr(app, "generate_financial_analysis", lambda **kwargs: "local financial text", raising=False)

    def fake_create_history(**kwargs):
        called["value"] = True
        return 1

    monkeypatch.setattr(app, "create_analysis_history_entry", fake_create_history, raising=False)

    client = app.app.test_client()
    resp = client.post(
        "/api/financial-analysis",
        json={
            "symbols": ["NVDA"],
            "stocks": [{"symbol": "NVDA", "realtime": {}, "financial": {}, "forecast": {}, "news": []}],
            "provider": "openai",
            "api_key": "",
            "model": "",
            "language": "zh",
        },
    )

    assert resp.status_code == 200
    assert called["value"] is False


def test_analysis_history_routes(monkeypatch):
    monkeypatch.setattr(
        app,
        "list_analysis_history_symbols",
        lambda limit=200: [
            {"symbol": "NVDA", "history_count": 2, "latest_created_at": "2026-02-10T00:00:00+00:00"},
            {"symbol": "AMD", "history_count": 1, "latest_created_at": "2026-02-09T00:00:00+00:00"},
        ],
        raising=False,
    )
    monkeypatch.setattr(
        app,
        "list_analysis_history_entries",
        lambda symbol, analysis_type=None, limit=100: [
            {
                "id": 10,
                "symbol": "NVDA",
                "symbols": ["NVDA", "AMD"],
                "analysis_type": "ai",
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "language": "zh",
                "analysis": "snapshot",
                "created_at": "2026-02-10T00:00:00+00:00",
            }
        ],
        raising=False,
    )

    client = app.app.test_client()
    symbols_resp = client.get("/api/analysis-history/symbols")
    list_resp = client.get("/api/analysis-history?symbol=nvda&type=ai&limit=20")

    assert symbols_resp.status_code == 200
    assert symbols_resp.get_json()["items"][0]["symbol"] == "NVDA"

    assert list_resp.status_code == 200
    data = list_resp.get_json()
    assert data["symbol"] == "NVDA"
    assert data["analysis_type"] == "ai"
    assert data["items"][0]["analysis"] == "snapshot"


def test_analysis_history_route_requires_symbol():
    client = app.app.test_client()
    resp = client.get("/api/analysis-history")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_history_page_route_renders():
    client = app.app.test_client()
    resp = client.get("/history")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="history-symbol-input"' in html
    assert 'id="history-list"' in html
    assert "history.js" in html


def test_investment_note_routes(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        app,
        "create_investment_note",
        lambda symbol, content: 88 if captured.setdefault("create", (symbol, content)) else 0,
        raising=False,
    )
    monkeypatch.setattr(
        app,
        "list_investment_notes",
        lambda symbol, limit=200: [
            {
                "id": 88,
                "symbol": str(symbol).upper(),
                "content": "持仓纪律：跌破阈值减仓。",
                "created_at": "2026-02-10T12:00:00+00:00",
                "updated_at": "2026-02-10T12:00:00+00:00",
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        app,
        "list_investment_note_symbols",
        lambda limit=200: [
            {"symbol": "NVDA", "note_count": 2, "latest_created_at": "2026-02-10T12:00:00+00:00"},
            {"symbol": "AMD", "note_count": 1, "latest_created_at": "2026-02-09T12:00:00+00:00"},
        ],
        raising=False,
    )
    monkeypatch.setattr(app, "delete_investment_note", lambda note_id: int(note_id) == 88, raising=False)

    client = app.app.test_client()
    create_resp = client.post("/api/investment-notes", json={"symbol": "nvda", "content": "持仓纪律：跌破阈值减仓。"})
    list_resp = client.get("/api/investment-notes?symbol=NVDA")
    symbols_resp = client.get("/api/investment-notes/symbols")
    delete_resp = client.delete("/api/investment-notes/88")

    assert create_resp.status_code == 200
    assert create_resp.get_json()["id"] == 88
    assert captured["create"] == ("NVDA", "持仓纪律：跌破阈值减仓。")

    assert list_resp.status_code == 200
    assert list_resp.get_json()["symbol"] == "NVDA"
    assert list_resp.get_json()["items"][0]["content"] == "持仓纪律：跌破阈值减仓。"

    assert symbols_resp.status_code == 200
    assert symbols_resp.get_json()["items"][0]["symbol"] == "NVDA"
    assert delete_resp.status_code == 200
    assert delete_resp.get_json()["ok"] is True


def test_investment_note_create_requires_symbol_and_content():
    client = app.app.test_client()
    no_symbol = client.post("/api/investment-notes", json={"content": "x"})
    no_content = client.post("/api/investment-notes", json={"symbol": "NVDA", "content": "   "})

    assert no_symbol.status_code == 400
    assert no_content.status_code == 400
    assert "error" in no_symbol.get_json()
    assert "error" in no_content.get_json()


def test_investment_note_list_requires_symbol():
    client = app.app.test_client()
    resp = client.get("/api/investment-notes")

    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_investment_note_delete_not_found(monkeypatch):
    monkeypatch.setattr(app, "delete_investment_note", lambda note_id: False, raising=False)
    client = app.app.test_client()

    resp = client.delete("/api/investment-notes/999")

    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False
    assert "error" in resp.get_json()

