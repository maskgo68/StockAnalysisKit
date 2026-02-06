from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
import os
import subprocess
import sys

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file

from stock_service import (
    generate_ai_investment_advice,
    get_stock_bundle,
    test_ai_provider,
    test_finnhub_api_key,
)

DEFAULT_SYMBOLS = ["NVDA"]

app = Flask(__name__)


def parse_symbols(raw: str):
    if not raw:
        return DEFAULT_SYMBOLS
    symbols = []
    for token in raw.replace("，", ",").split(","):
        symbol = token.strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols[:10] if symbols else DEFAULT_SYMBOLS


def fetch_multiple_stocks(symbols, finnhub_api_key):
    results = []
    with ThreadPoolExecutor(max_workers=min(8, len(symbols) or 1)) as pool:
        future_map = {pool.submit(get_stock_bundle, symbol, finnhub_api_key): symbol for symbol in symbols}
        for future in as_completed(future_map):
            symbol = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    {
                        "symbol": symbol,
                        "error": f"抓取失败: {exc}",
                        "realtime": {},
                        "financial": {},
                        "forecast": {},
                        "news": [],
                    }
                )

    order = {s: i for i, s in enumerate(symbols)}
    results.sort(key=lambda item: order.get(item.get("symbol", ""), 999))
    return results


def _build_export_rows(stocks, section, metric_map):
    rows = []
    for stock in stocks:
        row = {"symbol": stock.get("symbol")}
        data = stock.get(section, {}) or {}
        for key, label in metric_map.items():
            row[label] = data.get(key)
        rows.append(row)
    return rows


def _build_excel_file(stocks, symbols):
    realtime_map = {
        "price": "股价(USD)",
        "change_pct": "涨跌幅(%)",
        "market_cap_b": "总市值(B USD)",
        "turnover_b": "成交额(B USD)",
        "pe_ttm": "PE TTM",
        "change_5d_pct": "5日涨跌幅(%)",
        "change_20d_pct": "20日涨跌幅(%)",
    }
    financial_map = {
        "revenue_b": "营收(B USD)",
        "revenue_yoy_pct": "营收YoY(%)",
        "net_income_b": "利润(B USD)",
        "net_income_yoy_pct": "利润YoY(%)",
        "eps": "EPS(USD/股)",
        "gross_margin_pct": "毛利率(%)",
        "net_margin_pct": "净利率(%)",
    }
    forecast_map = {
        "forward_pe": "Forward PE",
        "peg": "PEG",
        "eps_forecast": "预测EPS(USD/股)",
        "eps_forecast_yoy_pct": "预测EPS YoY(%)",
    }

    realtime_df = pd.DataFrame(_build_export_rows(stocks, "realtime", realtime_map))
    financial_df = pd.DataFrame(_build_export_rows(stocks, "financial", financial_map))
    forecast_df = pd.DataFrame(_build_export_rows(stocks, "forecast", forecast_map))
    meta_df = pd.DataFrame(
        [
            {
                "symbols": ",".join(symbols),
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "note": "金额单位统一为十亿美元(B USD)，百分比字段单位为%",
            }
        ]
    )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        realtime_df.to_excel(writer, index=False, sheet_name="realtime")
        financial_df.to_excel(writer, index=False, sheet_name="financial")
        forecast_df.to_excel(writer, index=False, sheet_name="forecast")
        meta_df.to_excel(writer, index=False, sheet_name="meta")
    output.seek(0)
    return output


def _symbols_from_payload(payload):
    symbols_raw = payload.get("symbols")
    if isinstance(symbols_raw, list):
        return parse_symbols(",".join(str(s) for s in symbols_raw))
    return parse_symbols(str(symbols_raw or ""))


@app.get("/")
def index():
    return render_template("index.html", default_symbols=",".join(DEFAULT_SYMBOLS))


@app.get("/api/compare")
def compare():
    finnhub_api_key = request.headers.get("X-Finnhub-Api-Key", "").strip()
    if not finnhub_api_key:
        return jsonify({"error": "请先在前端填写 Finnhub API Key。"}), 400

    symbols = parse_symbols(request.args.get("symbols", ""))
    stocks = fetch_multiple_stocks(symbols, finnhub_api_key)
    return jsonify(
        {
            "symbols": symbols,
            "stocks": stocks,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.post("/api/export-excel")
def export_excel():
    payload = request.get_json(silent=True) or {}
    finnhub_api_key = str(payload.get("finnhub_api_key", "")).strip()
    if not finnhub_api_key:
        return jsonify({"error": "请先在前端填写 Finnhub API Key。"}), 400

    symbols = _symbols_from_payload(payload)
    stocks = fetch_multiple_stocks(symbols, finnhub_api_key)
    stream = _build_excel_file(stocks, symbols)
    filename = f"stock_compare_{'_'.join(symbols)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/ai-analysis")
def ai_analysis():
    payload = request.get_json(silent=True) or {}
    symbols = _symbols_from_payload(payload)

    stocks = payload.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        finnhub_api_key = str(payload.get("finnhub_api_key", "")).strip()
        if not finnhub_api_key:
            return jsonify({"error": "缺少 stocks 数据时必须提供 Finnhub API Key。"}), 400
        stocks = fetch_multiple_stocks(symbols, finnhub_api_key)

    provider = str(payload.get("provider", "gemini")).strip().lower()
    api_key = str(payload.get("api_key", "")).strip()
    model = str(payload.get("model", "")).strip()
    base_url = str(payload.get("base_url", "")).strip() or None

    analysis = generate_ai_investment_advice(
        symbols=symbols,
        stocks=stocks,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )

    return jsonify(
        {
            "symbols": symbols,
            "provider": provider,
            "model": model,
            "analysis": analysis,
        }
    )


@app.post("/api/test-config")
def test_config():
    payload = request.get_json(silent=True) or {}
    target = str(payload.get("target", "")).strip().lower()

    if target == "finnhub":
        ok, message = test_finnhub_api_key(str(payload.get("finnhub_api_key", "")).strip())
        return jsonify({"ok": ok, "message": message}), (200 if ok else 400)

    if target == "ai":
        ok, message = test_ai_provider(
            provider=str(payload.get("provider", "gemini")).strip().lower(),
            api_key=str(payload.get("api_key", "")).strip(),
            model=str(payload.get("model", "")).strip(),
            base_url=str(payload.get("base_url", "")).strip() or None,
        )
        return jsonify({"ok": ok, "message": message}), (200 if ok else 400)

    return jsonify({"ok": False, "message": "target 仅支持 finnhub 或 ai"}), 400


def _run_server():
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)


if __name__ == "__main__":
    spawn_in_new_console = (
        os.name == "nt"
        and os.environ.get("STOCKCOMPARE_SERVER_CHILD") != "1"
        and "--serve" not in sys.argv
    )

    if spawn_in_new_console:
        child_env = os.environ.copy()
        child_env["STOCKCOMPARE_SERVER_CHILD"] = "1"
        subprocess.Popen(
            [sys.executable, __file__, "--serve"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            env=child_env,
        )
        print("Server started in a new terminal window.")
    else:
        _run_server()
