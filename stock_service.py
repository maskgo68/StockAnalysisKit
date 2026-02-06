import json
import math
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}

def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isnan(value)


def _to_billions(value):
    if not _is_number(value):
        return None
    return round(float(value) / 1_000_000_000, 2)


def _round(value, digits=2):
    if not _is_number(value):
        return None
    return round(float(value), digits)


def _pct_change(new, old):
    if not _is_number(new) or not _is_number(old) or float(old) == 0:
        return None
    return round((float(new) / float(old) - 1) * 100, 2)


def _extract_raw(obj, path):
    node = obj
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if isinstance(node, dict) and "raw" in node:
        return node.get("raw")
    return node


def _parse_display_number(text):
    if not text:
        return None
    v = str(text).strip().replace(",", "")
    if v in {"N/A", "--"}:
        return None
    is_pct = v.endswith("%")
    if is_pct:
        v = v[:-1]

    multiplier = 1.0
    if v.endswith("T"):
        multiplier = 1_000_000_000_000
        v = v[:-1]
    elif v.endswith("B"):
        multiplier = 1_000_000_000
        v = v[:-1]
    elif v.endswith("M"):
        multiplier = 1_000_000
        v = v[:-1]
    elif v.endswith("K"):
        multiplier = 1_000
        v = v[:-1]

    try:
        num = float(v)
        return num if is_pct else num * multiplier
    except Exception:
        return None


def _finnhub_get(path, params, api_key):
    if not api_key:
        raise ValueError("未提供 Finnhub API Key。")
    p = dict(params or {})
    p["token"] = api_key
    url = f"https://finnhub.io/api/v1{path}"
    resp = requests.get(url, params=p, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _safe_finnhub_get(path, params, api_key):
    try:
        return _finnhub_get(path, params, api_key), None
    except Exception as exc:
        return {}, str(exc)


def _yahoo_chart_prices(symbol, range_str="3mo", interval="1d"):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval={interval}"
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        result = (data.get("chart") or {}).get("result") or []
        if not result:
            return [], []
        q = (((result[0].get("indicators") or {}).get("quote") or [{}])[0] or {})
        closes = [float(x) for x in (q.get("close") or []) if _is_number(x)]
        volumes = [float(x) for x in (q.get("volume") or []) if _is_number(x)]
        return closes, volumes
    except Exception:
        return [], []


def _finnhub_bundle(symbol, api_key):
    quote, e_quote = _safe_finnhub_get("/quote", {"symbol": symbol}, api_key)
    profile, e_profile = _safe_finnhub_get("/stock/profile2", {"symbol": symbol}, api_key)
    metric_resp, e_metric = _safe_finnhub_get("/stock/metric", {"symbol": symbol, "metric": "all"}, api_key)
    metric = metric_resp.get("metric", {}) if isinstance(metric_resp, dict) else {}
    financials, e_fin = _safe_finnhub_get("/stock/financials-reported", {"symbol": symbol, "freq": "annual"}, api_key)
    # 某些 Finnhub 套餐无 candle 权限，降级到 Yahoo chart 只用于补齐5日/20日与成交额
    closes, volumes = _yahoo_chart_prices(symbol)

    return {
        "quote": quote,
        "profile": profile,
        "metric": metric,
        "closes": closes,
        "volumes": volumes,
        "financials": financials,
        "errors": {
            "quote": e_quote,
            "profile": e_profile,
            "metric": e_metric,
            "financials": e_fin,
        },
    }


def _parse_yahoo_single_page(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    display_metrics = {}
    for li in soup.find_all("li"):
        label_node = li.find("p", class_=lambda x: x and "label" in x) or li.find(
            "span", class_=lambda x: x and "label" in x
        )
        value_node = li.find("p", class_=lambda x: x and "value" in x) or li.find(
            "span", class_=lambda x: x and "value" in x
        )
        if not label_node or not value_node:
            continue
        label = " ".join(label_node.get_text(" ", strip=True).split())
        val = _parse_display_number(" ".join(value_node.get_text(" ", strip=True).split()))
        if label and val is not None and label not in display_metrics:
            display_metrics[label] = val

    quote_summary = {}
    for script in soup.find_all("script", {"type": "application/json"}):
        txt = script.string or script.text or ""
        if "quoteSummary" not in txt or '"body"' not in txt:
            continue
        try:
            outer = json.loads(txt)
            body = outer.get("body")
            if isinstance(body, str) and "quoteSummary" in body:
                inner = json.loads(body)
                result = (inner.get("quoteSummary") or {}).get("result") or []
                if result and isinstance(result[0], dict):
                    quote_summary = result[0]
                    break
        except Exception:
            continue

    return {"display_metrics": display_metrics, "quote_summary": quote_summary}


def _parse_yahoo_pages(symbol):
    urls = [
        f"https://finance.yahoo.com/quote/{symbol}/",
        f"https://finance.yahoo.com/quote/{symbol}/key-statistics/",
        f"https://finance.yahoo.com/quote/{symbol}/analysis/",
    ]
    merged_metrics = {}
    merged_summary = {}
    for url in urls:
        try:
            res = _parse_yahoo_single_page(url)
            for k, v in (res.get("display_metrics") or {}).items():
                if k not in merged_metrics:
                    merged_metrics[k] = v
            if isinstance(res.get("quote_summary"), dict):
                merged_summary.update(res.get("quote_summary"))
        except Exception:
            continue
    return {"display_metrics": merged_metrics, "quote_summary": merged_summary}


def _extract_statement_value(items, concepts):
    if not isinstance(items, list):
        return None
    for c in concepts:
        for it in items:
            if it.get("concept") == c and _is_number(it.get("value")):
                return float(it.get("value"))
    return None


def _latest_two_annual_reports(financials_json):
    data = financials_json.get("data", []) if isinstance(financials_json, dict) else []
    rows = []
    for item in data:
        report = item.get("report", {}) if isinstance(item, dict) else {}
        end_date = item.get("endDate") or ""
        rows.append({"endDate": end_date, "ic": report.get("ic", [])})
    rows.sort(key=lambda x: x.get("endDate", ""), reverse=True)
    return rows[:2]


def _get_realtime_from_finnhub(bundle):
    quote = bundle.get("quote", {})
    profile = bundle.get("profile", {})
    metric = bundle.get("metric", {})
    closes = bundle.get("closes", []) if isinstance(bundle.get("closes"), list) else []
    volumes = bundle.get("volumes", []) if isinstance(bundle.get("volumes"), list) else []

    price = quote.get("c")
    prev_close = quote.get("pc")
    change_pct = quote.get("dp") if _is_number(quote.get("dp")) else _pct_change(price, prev_close)

    valid_closes = [float(x) for x in closes if _is_number(x)]

    c5 = _pct_change(valid_closes[-1], valid_closes[-6]) if len(valid_closes) >= 6 else None
    c20 = _pct_change(valid_closes[-1], valid_closes[-21]) if len(valid_closes) >= 21 else None

    turnover_b = None
    if len(valid_closes) > 0 and len(volumes) > 0 and _is_number(valid_closes[-1]) and _is_number(volumes[-1]):
        turnover_b = _to_billions(float(valid_closes[-1]) * float(volumes[-1]))

    mcap_million = profile.get("marketCapitalization")
    market_cap_b = round(float(mcap_million) / 1000, 2) if _is_number(mcap_million) else None

    eps_ttm = metric.get("epsTTM")
    pe_ttm = None
    if _is_number(price) and _is_number(eps_ttm) and float(eps_ttm) != 0:
        pe_ttm = float(price) / float(eps_ttm)
    if not _is_number(pe_ttm):
        pe_ttm = metric.get("peTTM")

    return {
        "price": _round(price),
        "change_pct": _round(change_pct),
        "market_cap_b": market_cap_b,
        "turnover_b": turnover_b,
        "pe_ttm": _round(pe_ttm),
        "change_5d_pct": c5,
        "change_20d_pct": c20,
    }


def _get_financial_from_finnhub(bundle):
    metric = bundle.get("metric", {})
    reports = _latest_two_annual_reports(bundle.get("financials", {}))

    revenue_latest = None
    revenue_prev = None
    net_income_latest = None
    net_income_prev = None
    gross_profit_latest = None
    eps = None

    revenue_concepts = [
        "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap_Revenues",
        "us-gaap_SalesRevenueNet",
    ]
    net_income_concepts = ["us-gaap_NetIncomeLoss", "us-gaap_ProfitLoss"]
    gross_profit_concepts = ["us-gaap_GrossProfit"]
    eps_concepts = ["us-gaap_EarningsPerShareDiluted", "us-gaap_EarningsPerShareBasic"]

    if len(reports) >= 1:
        revenue_latest = _extract_statement_value(reports[0].get("ic"), revenue_concepts)
        net_income_latest = _extract_statement_value(reports[0].get("ic"), net_income_concepts)
        gross_profit_latest = _extract_statement_value(reports[0].get("ic"), gross_profit_concepts)
        eps = _extract_statement_value(reports[0].get("ic"), eps_concepts)
    if len(reports) >= 2:
        revenue_prev = _extract_statement_value(reports[1].get("ic"), revenue_concepts)
        net_income_prev = _extract_statement_value(reports[1].get("ic"), net_income_concepts)

    if not _is_number(eps):
        eps = metric.get("epsTTM")

    gross_margin = metric.get("grossMarginAnnual")
    if _is_number(gross_margin):
        gross_margin = round(float(gross_margin), 2)
    elif _is_number(gross_profit_latest) and _is_number(revenue_latest) and revenue_latest != 0:
        gross_margin = round((gross_profit_latest / revenue_latest) * 100, 2)
    else:
        gross_margin = None

    net_margin = metric.get("netMarginAnnual")
    if _is_number(net_margin):
        net_margin = round(float(net_margin), 2)
    elif _is_number(net_income_latest) and _is_number(revenue_latest) and revenue_latest != 0:
        net_margin = round((net_income_latest / revenue_latest) * 100, 2)
    else:
        net_margin = None

    return {
        "revenue_b": _to_billions(revenue_latest),
        "revenue_yoy_pct": _pct_change(revenue_latest, revenue_prev),
        "net_income_b": _to_billions(net_income_latest),
        "net_income_yoy_pct": _pct_change(net_income_latest, net_income_prev),
        "eps": _round(eps),
        "gross_margin_pct": gross_margin,
        "net_margin_pct": net_margin,
    }


def _get_forecast_from_yahoo(symbol):
    page = _parse_yahoo_pages(symbol)
    metrics = page.get("display_metrics", {})
    qs = page.get("quote_summary", {})

    forward_pe = metrics.get("Forward P/E")
    if not _is_number(forward_pe):
        forward_pe = _extract_raw(qs, ["defaultKeyStatistics", "forwardPE"])

    peg = metrics.get("PEG Ratio (5yr expected)")
    if not _is_number(peg):
        peg = _extract_raw(qs, ["defaultKeyStatistics", "pegRatio"])

    eps_forecast = _extract_raw(qs, ["defaultKeyStatistics", "forwardEps"])
    eps_base = _extract_raw(qs, ["defaultKeyStatistics", "trailingEps"])

    return {
        "forward_pe": _round(forward_pe),
        "peg": _round(peg),
        "eps_forecast": _round(eps_forecast),
        "eps_forecast_yoy_pct": _pct_change(eps_forecast, eps_base),
    }


def _to_iso(ts):
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _fetch_news_finnhub(symbol, api_key, limit=5):
    try:
        to_date = datetime.now(timezone.utc).date()
        from_date = to_date - timedelta(days=14)
        data = _finnhub_get(
            "/company-news",
            {"symbol": symbol, "from": from_date.isoformat(), "to": to_date.isoformat()},
            api_key,
        )
        items = []
        for n in (data or [])[:limit]:
            items.append(
                {
                    "title": n.get("headline"),
                    "publisher": n.get("source"),
                    "link": n.get("url"),
                    "published_at": _to_iso(n.get("datetime")),
                }
            )
        return [i for i in items if i.get("title")]
    except Exception:
        return []


def _fetch_news_rss(symbol, limit=5):
    items = []
    try:
        url = f"https://finance.yahoo.com/rss/headline?s={symbol}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "xml")
        for node in soup.find_all("item")[:limit]:
            dt = None
            if node.pubDate and node.pubDate.text:
                try:
                    dt = parsedate_to_datetime(node.pubDate.text).astimezone(timezone.utc).isoformat()
                except Exception:
                    dt = None
            items.append(
                {
                    "title": node.title.text if node.title else None,
                    "publisher": "Yahoo Finance",
                    "link": node.link.text if node.link else None,
                    "published_at": dt,
                }
            )
    except Exception:
        pass
    return [i for i in items if i.get("title")]


def _get_recent_news(symbol, api_key, limit=5):
    news = _fetch_news_finnhub(symbol, api_key, limit=limit)
    if news:
        return news[:limit]
    return _fetch_news_rss(symbol, limit=limit)


def get_stock_bundle(symbol, finnhub_api_key):
    symbol = symbol.upper()

    finnhub_bundle = _finnhub_bundle(symbol, finnhub_api_key)
    realtime = _get_realtime_from_finnhub(finnhub_bundle)
    financial = _get_financial_from_finnhub(finnhub_bundle)

    try:
        forecast = _get_forecast_from_yahoo(symbol)
    except Exception:
        forecast = {
            "forward_pe": None,
            "peg": None,
            "eps_forecast": None,
            "eps_forecast_yoy_pct": None,
        }

    return {
        "symbol": symbol,
        "realtime": realtime,
        "financial": financial,
        "forecast": forecast,
        "news": _get_recent_news(symbol, finnhub_api_key, limit=5),
    }


def _compact_stock_context(stock):
    symbol = stock.get("symbol")
    rt = stock.get("realtime", {})
    fc = stock.get("forecast", {})
    news = stock.get("news", [])

    headline_lines = []
    for n in news[:5]:
        title = n.get("title")
        publisher = n.get("publisher") or ""
        published_at = n.get("published_at") or ""
        if title:
            headline_lines.append(f"- {title} | {publisher} | {published_at}")

    return (
        f"股票: {symbol}\n"
        f"近况参考: 日涨跌幅={rt.get('change_pct')}%, 5日={rt.get('change_5d_pct')}%, 20日={rt.get('change_20d_pct')}%\n"
        f"估值参考: PE(TTM)={rt.get('pe_ttm')}, Forward PE={fc.get('forward_pe')}, PEG={fc.get('peg')}\n"
        f"相关新闻:\n" + ("\n".join(headline_lines) if headline_lines else "- 无可用新闻")
    )


def _build_ai_prompt(symbols, stocks):
    blocks = [_compact_stock_context(stock) for stock in stocks if stock.get("symbol") in symbols]
    if not blocks:
        return None

    return f"""
你是美股投研分析师。请基于以下股票（{', '.join(symbols)}）的最新市场表现和新闻线索，给出可执行的投资建议。
要求：
1) 不要复述表格数据，重点做综合判断（行业趋势、催化剂、风险、估值性价比、仓位建议）。
2) 输出必须包含：结论排序（最看好->最谨慎）、每只股票的买入/观望/减持建议、3-6个月观点、主要风险点。
3) 如果信息不足，请明确写“信息不足”并指出还需要哪些信息。
4) 全文中文，避免空话。

股票上下文：
{chr(10).join(blocks)}
""".strip()


def _extract_openai_text(message):
    if isinstance(message, str):
        return message.strip()
    if not isinstance(message, list):
        return ""
    parts = []
    for part in message:
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
            parts.append(str(part.get("text")))
    return "".join(parts).strip()


def _call_gemini_once(prompt, api_key, model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4},
    }
    resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=40)
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        return "", ""
    first = candidates[0]
    parts = first.get("content", {}).get("parts", [])
    texts = [p.get("text", "") for p in parts if p.get("text")]
    return "\n".join(texts).strip(), str(first.get("finishReason", "")).lower()


def _call_openai_compatible_once(prompt, api_key, model, base_url):
    root = (base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{root}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是资深美股分析师，回答要中文、结构清晰、可执行。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=40,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return "", ""
    first = choices[0]
    message = first.get("message", {}).get("content")
    return _extract_openai_text(message), str(first.get("finish_reason", "")).lower()


def _call_claude_once(prompt, api_key, model):
    payload = {
        "model": model,
        "max_tokens": 8192,
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json=payload,
        timeout=40,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("content", [])
    texts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            texts.append(str(item.get("text")))
    return "\n".join(texts).strip(), str(data.get("stop_reason", "")).lower()


def _call_ai_once(provider_key, prompt, api_key, model, base_url=None):
    if provider_key == "gemini":
        return _call_gemini_once(prompt, api_key, model)
    if provider_key == "claude":
        return _call_claude_once(prompt, api_key, model)
    if provider_key == "openai":
        return _call_openai_compatible_once(prompt, api_key, model, base_url)
    raise ValueError(f"不支持的 AI Provider: {provider_key}")


def _is_truncated_reason(reason):
    r = (reason or "").lower()
    return r in {"length", "max_tokens", "token_limit", "max_output_tokens", "model_length"}


def generate_ai_investment_advice(symbols, stocks, provider, api_key, model, base_url=None):
    if not api_key:
        return "未配置 AI API Key，无法生成投资建议。"
    if not model:
        return "未配置 AI 模型名，无法生成投资建议。"

    prompt = _build_ai_prompt(symbols, stocks)
    if not prompt:
        return "缺少可分析的股票上下文，无法生成建议。"

    try:
        provider_key = (provider or "").strip().lower()
        if provider_key not in {"openai", "gemini", "claude"}:
            return f"不支持的 AI Provider: {provider}"

        full_text = ""
        next_prompt = prompt

        # 自动续写，直到非截断结束；上限用于避免极端情况下无限循环。
        for _ in range(8):
            text, finish_reason = _call_ai_once(provider_key, next_prompt, api_key, model, base_url)
            text = (text or "").strip()
            if text:
                full_text = (full_text + "\n\n" + text).strip() if full_text else text

            if not _is_truncated_reason(finish_reason):
                break

            next_prompt = (
                "你刚才的回答因为长度限制被截断了。请只继续未完成的部分，"
                "不要重复已经写过的内容，并写到完整收尾。"
            )

        return full_text or "AI 返回为空。"
    except Exception as exc:
        return f"AI 调用失败: {exc}"


def test_finnhub_api_key(api_key):
    if not api_key:
        return False, "请填写 Finnhub API Key。"
    try:
        data = _finnhub_get("/quote", {"symbol": "AAPL"}, api_key)
        if isinstance(data, dict) and _is_number(data.get("c")):
            return True, "Finnhub 配置可用。"
        return False, "Finnhub 返回格式异常，请检查 Key 或套餐权限。"
    except Exception as exc:
        return False, f"Finnhub 测试失败: {exc}"


def test_ai_provider(provider, api_key, model, base_url=None):
    if not api_key:
        return False, "请填写 AI API Key。"
    if not model:
        return False, "请填写 AI 模型名。"
    probe_prompt = "请回复“OK”两个字，不要包含其他内容。"
    try:
        provider_key = (provider or "").strip().lower()
        if provider_key not in {"openai", "gemini", "claude"}:
            return False, f"不支持的 AI Provider: {provider}"
        text, _ = _call_ai_once(provider_key, probe_prompt, api_key, model, base_url)
        return (True, "AI 配置可用。") if text else (False, "AI 返回为空，请检查模型权限。")
    except Exception as exc:
        return False, f"AI 测试失败: {exc}"
