from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
from io import BytesIO
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file

from persistence import (
    create_watchlist_entry,
    delete_watchlist_entry,
    get_watchlist_entry,
    init_storage,
    list_watchlist_entries,
    update_watchlist_entry_name,
)
from stock_service import (
    generate_financial_analysis,
    generate_ai_investment_advice,
    generate_target_price_analysis,
    generate_ai_investment_followup,
    generate_financial_analysis_followup,
    get_stock_bundle,
    test_ai_provider,
    test_exa_api_key,
    test_finnhub_api_key,
    test_tavily_api_key,
)

PID_FILE = Path(__file__).resolve().parent / ".stockanalysiskit-server.pid"
APP_PORT = 16888

app = Flask(__name__)
init_storage()


def parse_symbols(raw: str):
    if not raw:
        return []
    symbols = []
    for token in raw.replace("，", ",").split(","):
        symbol = token.strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols[:10]


def _is_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _payload_or_env(payload, key, env_name):
    value = str((payload or {}).get(key, "")).strip()
    if value:
        return value
    return str(os.getenv(env_name, "")).strip()


def fetch_multiple_stocks(
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
    results = []
    with ThreadPoolExecutor(max_workers=min(8, len(symbols) or 1)) as pool:
        future_map = {
            pool.submit(
                get_stock_bundle,
                symbol,
                finnhub_api_key,
                force_refresh_financial=force_refresh_financial,
                exa_api_key=exa_api_key,
                tavily_api_key=tavily_api_key,
                ai_provider=ai_provider,
                ai_api_key=ai_api_key,
                ai_model=ai_model,
                ai_base_url=ai_base_url,
            ): symbol
            for symbol in symbols
        }
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
                        "expectation_guidance": {},
                    }
                )

    order = {s: i for i, s in enumerate(symbols)}
    results.sort(key=lambda item: order.get(item.get("symbol", ""), 999))
    return results


def _fetch_multiple_stocks_compat(
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
    try:
        return fetch_multiple_stocks(
            symbols,
            finnhub_api_key,
            force_refresh_financial=force_refresh_financial,
            exa_api_key=exa_api_key,
            tavily_api_key=tavily_api_key,
            ai_provider=ai_provider,
            ai_api_key=ai_api_key,
            ai_model=ai_model,
            ai_base_url=ai_base_url,
        )
    except TypeError as exc:
        # 测试替身可能使用旧签名，不接受新参数。
        if not any(
            key in str(exc)
            for key in (
                "exa_api_key",
                "tavily_api_key",
                "ai_provider",
                "ai_api_key",
                "ai_model",
                "ai_base_url",
            )
        ):
            raise
        return fetch_multiple_stocks(
            symbols,
            finnhub_api_key,
            force_refresh_financial=force_refresh_financial,
        )


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
        "change_250d_pct": "250日涨跌幅(%)",
    }
    financial_map = {
        "latest_period": "最新财报期",
        "latest_report_date": "财报公布日期",
        "latest_period_type": "财报类型(quarterly/annual)",
        "revenue_b": "营收(B USD)",
        "revenue_yoy_pct": "营收YoY(%)",
        "net_income_b": "利润(B USD)",
        "net_income_yoy_pct": "利润YoY(%)",
        "eps": "EPS(USD/股)",
        "gross_margin_pct": "毛利率(%)",
        "operating_margin_pct": "经营利润率(%)",
        "net_margin_pct": "净利率(%)",
    }
    forecast_map = {
        "forward_pe": "Forward PE",
        "peg": "PEG",
        "ev_to_ebitda": "EV/EBITDA",
        "ps": "P/S (TTM)",
        "pb": "P/B",
        "eps_forecast": "预测EPS(USD/股)",
        "next_year_eps_forecast": "预测EPS(Next Year)",
        "next_quarter_eps_forecast": "下季度预测EPS(USD/股)",
        "next_earnings_date": "下季度财报日期",
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


def _build_analysis_request_context(payload):
    payload = payload or {}
    return {
        "symbols": _symbols_from_payload(payload),
        "finnhub_api_key": str(payload.get("finnhub_api_key", "")).strip(),
        "force_refresh_financial": _is_truthy(payload.get("force_financial_refresh")),
        "provider": str(payload.get("provider", "gemini")).strip().lower(),
        "api_key": str(payload.get("api_key", "")).strip(),
        "model": str(payload.get("model", "")).strip(),
        "base_url": str(payload.get("base_url", "")).strip() or None,
        "exa_api_key": _payload_or_env(payload, "exa_api_key", "EXA_API_KEY"),
        "tavily_api_key": _payload_or_env(payload, "tavily_api_key", "TAVILY_API_KEY"),
    }


def _stocks_need_ai_context(stocks):
    return any(
        not isinstance((stock or {}).get("ai_financial_context"), dict)
        or not (stock or {}).get("ai_financial_context", {}).get("annual")
        or not (stock or {}).get("ai_financial_context", {}).get("quarterly")
        for stock in stocks
        if isinstance(stock, dict)
    )


def _fetch_analysis_stocks(context):
    return _fetch_multiple_stocks_compat(
        context.get("symbols", []),
        context.get("finnhub_api_key", ""),
        force_refresh_financial=context.get("force_refresh_financial", False),
        exa_api_key=context.get("exa_api_key"),
        tavily_api_key=context.get("tavily_api_key"),
        ai_provider=context.get("provider"),
        ai_api_key=context.get("api_key"),
        ai_model=context.get("model"),
        ai_base_url=context.get("base_url"),
    )


def _resolve_analysis_stocks(context, stocks=None, require_ai_context=False):
    if not isinstance(stocks, list) or not stocks:
        return _fetch_analysis_stocks(context)
    if require_ai_context and _stocks_need_ai_context(stocks):
        return _fetch_analysis_stocks(context)
    return stocks


@app.get("/")
def index():
    return render_template("index.html", default_symbols="")


@app.get("/api/compare")
def compare():
    finnhub_api_key = request.headers.get("X-Finnhub-Api-Key", "").strip()
    exa_api_key = request.headers.get("X-Exa-Api-Key", "").strip()
    tavily_api_key = request.headers.get("X-Tavily-Api-Key", "").strip()
    ai_provider = request.headers.get("X-AI-Provider", "").strip().lower() or None
    ai_api_key = request.headers.get("X-AI-Api-Key", "").strip()
    ai_model = request.headers.get("X-AI-Model", "").strip()
    ai_base_url = request.headers.get("X-AI-Base-Url", "").strip() or None

    symbols = parse_symbols(request.args.get("symbols", ""))
    force_refresh_financial = _is_truthy(request.args.get("force_financial_refresh"))
    stocks = _fetch_multiple_stocks_compat(
        symbols,
        finnhub_api_key,
        force_refresh_financial=force_refresh_financial,
        exa_api_key=exa_api_key,
        tavily_api_key=tavily_api_key,
        ai_provider=ai_provider,
        ai_api_key=ai_api_key,
        ai_model=ai_model,
        ai_base_url=ai_base_url,
    )
    response = jsonify(
        {
            "symbols": symbols,
            "stocks": stocks,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    response.headers["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.post("/api/export-excel")
def export_excel():
    payload = request.get_json(silent=True) or {}
    finnhub_api_key = str(payload.get("finnhub_api_key", "")).strip()

    symbols = _symbols_from_payload(payload)
    stocks = _fetch_multiple_stocks_compat(
        symbols,
        finnhub_api_key,
        force_refresh_financial=_is_truthy(payload.get("force_financial_refresh")),
    )
    stream = _build_excel_file(stocks, symbols)
    filename = f"stockanalysiskit_{'_'.join(symbols)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/ai-analysis")
def ai_analysis():
    payload = request.get_json(silent=True) or {}
    context = _build_analysis_request_context(payload)
    stocks = _resolve_analysis_stocks(
        context=context,
        stocks=payload.get("stocks"),
        require_ai_context=True,
    )

    analysis = generate_ai_investment_advice(
        symbols=context["symbols"],
        stocks=stocks,
        provider=context["provider"],
        api_key=context["api_key"],
        model=context["model"],
        base_url=context["base_url"],
        exa_api_key=context["exa_api_key"],
        tavily_api_key=context["tavily_api_key"],
    )

    return jsonify(
        {
            "symbols": context["symbols"],
            "provider": context["provider"],
            "model": context["model"],
            "analysis": analysis,
        }
    )


@app.post("/api/financial-analysis")
def financial_analysis():
    payload = request.get_json(silent=True) or {}
    context = _build_analysis_request_context(payload)
    stocks = _resolve_analysis_stocks(
        context=context,
        stocks=payload.get("stocks"),
        require_ai_context=False,
    )

    analysis = generate_financial_analysis(
        symbols=context["symbols"],
        stocks=stocks,
        provider=context["provider"],
        api_key=context["api_key"],
        model=context["model"],
        base_url=context["base_url"],
        exa_api_key=context["exa_api_key"],
        tavily_api_key=context["tavily_api_key"],
    )
    return jsonify(
        {
            "symbols": context["symbols"],
            "analysis": analysis,
            "provider": context["provider"] if context["api_key"] and context["model"] else None,
            "model": context["model"] if context["api_key"] and context["model"] else None,
        }
    )


@app.post("/api/target-price-analysis")
def target_price_analysis():
    payload = request.get_json(silent=True) or {}
    context = _build_analysis_request_context(payload)
    stocks = _resolve_analysis_stocks(
        context=context,
        stocks=payload.get("stocks"),
        require_ai_context=True,
    )

    analysis = generate_target_price_analysis(
        symbols=context["symbols"],
        stocks=stocks,
        provider=context["provider"],
        api_key=context["api_key"],
        model=context["model"],
        base_url=context["base_url"],
        exa_api_key=context["exa_api_key"],
        tavily_api_key=context["tavily_api_key"],
    )
    return jsonify(
        {
            "symbols": context["symbols"],
            "analysis": analysis,
            "provider": context["provider"] if context["api_key"] and context["model"] else None,
            "model": context["model"] if context["api_key"] and context["model"] else None,
        }
    )


@app.post("/api/financial-analysis-followup")
def financial_analysis_followup():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    if not question:
        return jsonify({"error": "追问内容不能为空。"}), 400

    context = _build_analysis_request_context(payload)
    base_analysis = str(payload.get("base_analysis", "")).strip()
    history = payload.get("history")
    stocks = _resolve_analysis_stocks(
        context=context,
        stocks=payload.get("stocks"),
        require_ai_context=False,
    )

    answer = generate_financial_analysis_followup(
        symbols=context["symbols"],
        stocks=stocks,
        provider=context["provider"],
        api_key=context["api_key"],
        model=context["model"],
        base_url=context["base_url"],
        base_analysis=base_analysis,
        history=history,
        question=question,
    )

    return jsonify(
        {
            "symbols": context["symbols"],
            "provider": context["provider"],
            "model": context["model"],
            "answer": answer,
        }
    )


@app.post("/api/ai-analysis-followup")
def ai_analysis_followup():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    if not question:
        return jsonify({"error": "追问内容不能为空。"}), 400

    context = _build_analysis_request_context(payload)
    base_analysis = str(payload.get("base_analysis", "")).strip()
    history = payload.get("history")
    stocks = _resolve_analysis_stocks(
        context=context,
        stocks=payload.get("stocks"),
        require_ai_context=True,
    )

    answer = generate_ai_investment_followup(
        symbols=context["symbols"],
        stocks=stocks,
        provider=context["provider"],
        api_key=context["api_key"],
        model=context["model"],
        base_url=context["base_url"],
        base_analysis=base_analysis,
        history=history,
        question=question,
    )

    return jsonify(
        {
            "symbols": context["symbols"],
            "provider": context["provider"],
            "model": context["model"],
            "answer": answer,
        }
    )


@app.get("/api/watchlist")
def get_watchlist():
    return jsonify({"items": list_watchlist_entries(limit=200)})


@app.post("/api/watchlist")
def save_watchlist():
    payload = request.get_json(silent=True) or {}
    symbols = _symbols_from_payload(payload)
    if not symbols:
        return jsonify({"error": "请先添加至少1个股票代码后再保存。"}), 400

    watchlist_name = str(payload.get("name", "")).strip()
    new_id = create_watchlist_entry(watchlist_name, symbols)
    item = get_watchlist_entry(new_id) if new_id else None
    if not item:
        return jsonify({"error": "保存失败"}), 500
    return jsonify(item)


@app.get("/api/watchlist/<int:watchlist_id>")
def watchlist_detail(watchlist_id):
    item = get_watchlist_entry(watchlist_id)
    if not item:
        return jsonify({"error": "自选组不存在"}), 404
    return jsonify(item)


@app.delete("/api/watchlist/<int:watchlist_id>")
def watchlist_delete(watchlist_id):
    ok = delete_watchlist_entry(watchlist_id)
    return jsonify({"ok": ok})


@app.patch("/api/watchlist/<int:watchlist_id>")
def watchlist_rename(watchlist_id):
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    if not name:
        return jsonify({"error": "自选组名称不能为空"}), 400

    item = update_watchlist_entry_name(watchlist_id, name)
    if not item:
        return jsonify({"error": "自选组不存在"}), 404
    return jsonify(item)


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

    if target == "exa":
        ok, message = test_exa_api_key(_payload_or_env(payload, "exa_api_key", "EXA_API_KEY"))
        return jsonify({"ok": ok, "message": message}), (200 if ok else 400)

    if target == "tavily":
        ok, message = test_tavily_api_key(_payload_or_env(payload, "tavily_api_key", "TAVILY_API_KEY"))
        return jsonify({"ok": ok, "message": message}), (200 if ok else 400)

    return jsonify({"ok": False, "message": "target 仅支持 finnhub、ai、exa 或 tavily"}), 400


def _read_pid_file():
    try:
        raw = PID_FILE.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except Exception:
        return None


def _write_pid_file(pid):
    try:
        PID_FILE.write_text(str(int(pid)), encoding="utf-8")
    except Exception:
        pass


def _remove_pid_file(expected_pid=None):
    try:
        if not PID_FILE.exists():
            return
        if expected_pid is not None:
            current = _read_pid_file()
            if current is not None and int(current) != int(expected_pid):
                return
        PID_FILE.unlink()
    except Exception:
        pass


def _is_process_running(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or "").strip()
            if not output or "No tasks are running" in output:
                return False
            first_line = output.splitlines()[0].strip()
            if not first_line or first_line.upper().startswith("INFO:"):
                return False
            return f'"{pid}"' in first_line
        except Exception:
            return False

    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _pid_listening_on_port(port):
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in (result.stdout or "").splitlines():
                parts = line.split()
                if len(parts) < 5 or parts[0].upper() != "TCP":
                    continue
                local_addr = parts[1]
                state = parts[3].upper()
                pid_text = parts[4]
                if local_addr.endswith(f":{port}") and state == "LISTENING" and pid_text.isdigit():
                    return int(pid_text)
            return None

        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in (result.stdout or "").splitlines():
            txt = line.strip()
            if txt.isdigit():
                return int(txt)
    except Exception:
        return None
    return None


def _print_status():
    pid = _read_pid_file()
    if pid and _is_process_running(pid):
        print(f"服务运行中: PID={pid}, URL=http://127.0.0.1:{APP_PORT}")
        return

    port_pid = _pid_listening_on_port(APP_PORT)
    if port_pid and _is_process_running(port_pid):
        print(f"服务运行中(端口探测): PID={port_pid}, URL=http://127.0.0.1:{APP_PORT}")
        return

    if pid and not _is_process_running(pid):
        _remove_pid_file()
        print(f"发现过期 PID 文件({pid})，已清理。")
    print("服务未运行。")


def _stop_server():
    pid = _read_pid_file()
    if not pid:
        pid = _pid_listening_on_port(APP_PORT)
        if not pid:
            print("服务未运行（未找到 PID 文件且端口未监听）。")
            return
        print(f"未找到 PID 文件，按端口识别到服务进程 PID={pid}。")
    if not _is_process_running(pid):
        _remove_pid_file()
        print(f"服务未运行（PID {pid} 不存在，已清理 PID 文件）。")
        return

    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "").strip() or "未知错误"
            print(f"停止失败: {msg}")
            return
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as exc:
            print(f"停止失败: {exc}")
            return

    for _ in range(40):
        if not _is_process_running(pid):
            break
        time.sleep(0.1)

    if _is_process_running(pid):
        print(f"停止请求已发送，但进程仍存在: PID={pid}")
        return

    _remove_pid_file(expected_pid=pid)
    print(f"服务已停止: PID={pid}")


def _run_server():
    existing_pid = _pid_listening_on_port(APP_PORT)
    if existing_pid and _is_process_running(existing_pid):
        print(f"端口 {APP_PORT} 已被进程占用: PID={existing_pid}")
        print("可先执行: python app.py --stop")
        return

    current_pid = os.getpid()
    _write_pid_file(current_pid)
    print(f"服务启动中: PID={current_pid}")
    print("状态查询: python app.py --status")
    print("停止服务: python app.py --stop")
    try:
        app.run(host="0.0.0.0", port=APP_PORT, debug=True, use_reloader=False)
    finally:
        _remove_pid_file(expected_pid=current_pid)


def _start_server_in_new_console():
    existing_pid = _pid_listening_on_port(APP_PORT)
    if existing_pid and _is_process_running(existing_pid):
        print(f"服务已在运行: PID={existing_pid}, URL=http://127.0.0.1:{APP_PORT}")
        print("可先执行: python app.py --stop")
        return

    script_path = Path(__file__).resolve()
    popen_kwargs = {"cwd": str(script_path.parent)}
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

    proc = subprocess.Popen([sys.executable, str(script_path), "--serve"], **popen_kwargs)
    print(f"已在新终端窗口启动服务: PID={getattr(proc, 'pid', '--')}")
    print("状态查询: python app.py --status")
    print("停止服务: python app.py --stop")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="美股分析助手服务管理")
    parser.add_argument("--status", action="store_true", help="查看服务状态")
    parser.add_argument("--stop", action="store_true", help="停止运行中的服务")
    parser.add_argument("--serve", action="store_true", help="在当前终端前台运行服务")
    return parser.parse_args(argv)


def _handle_cli(args):
    if args.status:
        _print_status()
    elif args.stop:
        _stop_server()
    elif args.serve:
        _run_server()
    elif os.name == "nt":
        _start_server_in_new_console()
    else:
        _run_server()


if __name__ == "__main__":
    _handle_cli(_parse_args())
