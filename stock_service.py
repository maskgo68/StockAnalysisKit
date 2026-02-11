import json
import logging
import math
import os
import re
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
import pandas as pd
import requests
from bs4 import BeautifulSoup
from persistence import get_cached_financial_bundle, set_cached_financial_bundle

try:
    import yfinance as yf
except Exception:
    yf = None

LOGGER = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}
AI_PROVIDER_TIMEOUT_SECONDS = 120
SEARCH_DEFAULT_MAX_RESULTS = 6
SEARCH_SNIPPET_MAX_LEN = 260


def _env_int(name, default):
    try:
        return int(str(os.getenv(name, default)).strip())
    except Exception:
        return int(default)


AI_AUTO_CONTINUE_MAX_ROUNDS = max(1, _env_int("AI_AUTO_CONTINUE_MAX_ROUNDS", 64))
AI_CLAUDE_MAX_TOKENS = max(1024, _env_int("AI_CLAUDE_MAX_TOKENS", 64000))
NEWS_ITEMS_PER_STOCK = max(1, min(_env_int("NEWS_ITEMS_PER_STOCK", 10), 20))
EXTERNAL_SEARCH_ITEMS_PER_STOCK = max(1, min(_env_int("EXTERNAL_SEARCH_ITEMS_PER_STOCK", 10), 20))
_FETCH_ISSUES = ContextVar("stock_fetch_issues", default=None)


def _issue_status_code(exc):
    if exc is None:
        return None
    try:
        response = getattr(exc, "response", None)
        code = getattr(response, "status_code", None)
        if code is None:
            return None
        return int(code)
    except Exception:
        return None


def _issue_message(exc=None, message=None):
    if message is not None and str(message).strip():
        return str(message).strip()
    if exc is None:
        return "unknown error"

    text = str(exc or "").strip() or type(exc).__name__
    status_code = _issue_status_code(exc)
    if status_code is not None:
        return f"HTTP {status_code} - {text}"
    return f"{type(exc).__name__}: {text}"


def _record_fetch_issue(source, exc=None, message=None):
    source_text = str(source or "unknown").strip() or "unknown"
    entry = {
        "source": source_text,
        "message": _issue_message(exc=exc, message=message),
    }
    status_code = _issue_status_code(exc)
    if status_code is not None:
        entry["status_code"] = status_code

    issues = _FETCH_ISSUES.get()
    if isinstance(issues, list):
        issues.append(entry)

    if exc is None:
        LOGGER.warning("Stock fetch issue source=%s message=%s", source_text, entry["message"])
    else:
        LOGGER.warning("Stock fetch issue source=%s message=%s", source_text, entry["message"], exc_info=True)
    return entry


def _start_issue_collection():
    return _FETCH_ISSUES.set([])


def _finish_issue_collection(token):
    items = _FETCH_ISSUES.get()
    _FETCH_ISSUES.reset(token)
    if not isinstance(items, list):
        return []

    out = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        message = str(item.get("message") or "").strip()
        status_code = item.get("status_code")
        key = (source, message, status_code)
        if key in seen:
            continue
        seen.add(key)
        row = {"source": source or "unknown", "message": message or "unknown error"}
        if status_code is not None:
            row["status_code"] = status_code
        out.append(row)
    return out


class ServiceError(Exception):
    def __init__(self, code, message, status_code=400):
        self.code = str(code or "SERVICE_ERROR")
        self.message = str(message or "service error")
        self.status_code = int(status_code)
        super().__init__(self.message)


def _normalize_ui_language(language):
    raw = str(language or "").strip().lower()
    if raw.startswith("en"):
        return "en"
    if raw.startswith("zh"):
        return "zh"
    return "zh"


def _is_english(language):
    return _normalize_ui_language(language) == "en"


def _localized_text(language, zh_text, en_text):
    return str(en_text) if _is_english(language) else str(zh_text)


def _service_error(code, language, zh_text, en_text, status_code=400):
    return ServiceError(
        code=code,
        message=_localized_text(language, zh_text, en_text),
        status_code=status_code,
    )


def _runtime_ai_error_to_service_error(err, language):
    text = str(err or "").strip()
    lowered = text.lower()
    if "unsupported ai provider" in lowered or "不支持的 ai provider" in text:
        return ServiceError(code="AI_PROVIDER_UNSUPPORTED", message=text, status_code=400)
    if "missing stock context" in lowered or "缺少可分析的股票上下文" in text:
        return ServiceError(code="STOCK_CONTEXT_MISSING", message=text, status_code=400)
    return ServiceError(code="AI_CALL_FAILED", message=text, status_code=502)

# Yahoo ticker suffix to quote currency fallback map.
SYMBOL_SUFFIX_CURRENCY_MAP = {
    "HK": "HKD",
    "SS": "CNY",
    "SZ": "CNY",
    "SH": "CNY",
    "BJ": "CNY",
    "T": "JPY",
    "KS": "KRW",
    "KQ": "KRW",
    "TW": "TWD",
    "TWO": "TWD",
    "L": "GBP",
    "PA": "EUR",
    "AS": "EUR",
    "BR": "EUR",
    "MI": "EUR",
    "DE": "EUR",
    "MC": "EUR",
    "HE": "EUR",
    "CO": "DKK",
    "ST": "SEK",
    "OL": "NOK",
    "SW": "CHF",
    "AX": "AUD",
    "TO": "CAD",
    "V": "CAD",
    "SI": "SGD",
    "NS": "INR",
    "BO": "INR",
    "BK": "THB",
    "JK": "IDR",
    "KL": "MYR",
    "VN": "VND",
    "SA": "BRL",
    "MX": "MXN",
    "JO": "ZAR",
    "TA": "ILS",
    "ME": "RUB",
    "BA": "ARS",
}


def _normalize_currency_code(value):
    text = re.sub(r"[^A-Z]", "", str(value or "").strip().upper())
    if len(text) != 3:
        return None
    return text


def _infer_currency_from_symbol(symbol):
    raw = str(symbol or "").strip().upper()
    if not raw:
        return None
    if "." in raw:
        base, suffix = raw.rsplit(".", 1)
        mapped = SYMBOL_SUFFIX_CURRENCY_MAP.get(suffix)
        if mapped:
            return mapped
        # US tickers can contain a dot for class shares like BF.B.
        if len(suffix) == 1 and base.isalpha():
            return "USD"
        return None
    return "USD"

def _compact_text(value, max_len=SEARCH_SNIPPET_MAX_LEN):
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3].rstrip() + "..."


def _safe_domain(url):
    try:
        host = urlparse(str(url or "")).netloc.lower().strip()
        return host or ""
    except Exception:
        return ""


def _to_utc_datetime(value):
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(normalized)
    except Exception:
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_search_item(provider, title, url, published_at=None, source=None, snippet=None):
    title_text = _compact_text(title, max_len=220)
    url_text = str(url or "").strip()
    if not title_text or not url_text:
        return None

    dt = _to_utc_datetime(published_at)
    published_text = dt.date().isoformat() if dt else str(published_at or "").strip()
    source_text = str(source or "").strip() or _safe_domain(url_text) or provider.upper()
    snippet_text = _compact_text(snippet, max_len=SEARCH_SNIPPET_MAX_LEN)

    return {
        "provider": str(provider or "").strip().lower(),
        "title": title_text,
        "url": url_text,
        "published_at": published_text,
        "source": source_text,
        "snippet": snippet_text,
    }


def _dedupe_search_items(items, limit=None):
    deduped = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("url") or "").strip().lower(), str(item.get("title") or "").strip().lower())
        if not key[0] and not key[1]:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    if isinstance(limit, int) and limit > 0:
        deduped = deduped[:limit]
    return deduped


def _search_with_exa(query, api_key, max_results=SEARCH_DEFAULT_MAX_RESULTS, lookback_days=60):
    query_text = str(query or "").strip()
    key_text = str(api_key or "").strip()
    if not query_text or not key_text:
        return []

    num_results = max(1, min(int(max_results or SEARCH_DEFAULT_MAX_RESULTS), 10))
    days = max(1, int(lookback_days or 60))
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")

    payload = {
        "query": query_text,
        "type": "auto",
        "numResults": num_results,
        "startPublishedDate": start_date,
    }
    headers = {"x-api-key": key_text, "Content-Type": "application/json"}

    try:
        resp = requests.post(
            "https://api.exa.ai/search",
            headers=headers,
            json=payload,
            timeout=AI_PROVIDER_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    out = []
    for row in data.get("results", []) or []:
        if not isinstance(row, dict):
            continue
        highlights = row.get("highlights") if isinstance(row.get("highlights"), list) else []
        snippet = row.get("summary") or (highlights[0] if highlights else "") or row.get("text")
        item = _normalize_search_item(
            provider="exa",
            title=row.get("title"),
            url=row.get("url"),
            published_at=row.get("publishedDate"),
            source=row.get("author"),
            snippet=snippet,
        )
        if item:
            out.append(item)
    return _dedupe_search_items(out, limit=num_results)


def _search_with_tavily(query, api_key, max_results=SEARCH_DEFAULT_MAX_RESULTS, lookback_days=60):
    query_text = str(query or "").strip()
    key_text = str(api_key or "").strip()
    if not query_text or not key_text:
        return []

    num_results = max(1, min(int(max_results or SEARCH_DEFAULT_MAX_RESULTS), 10))
    days = max(1, int(lookback_days or 60))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    payload = {
        "api_key": key_text,
        "query": query_text,
        "search_depth": "advanced",
        "max_results": num_results,
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=AI_PROVIDER_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    out = []
    for row in data.get("results", []) or []:
        if not isinstance(row, dict):
            continue
        published = row.get("published_date") or row.get("publishedDate")
        published_dt = _to_utc_datetime(published)
        if published_dt and published_dt < cutoff:
            continue
        item = _normalize_search_item(
            provider="tavily",
            title=row.get("title"),
            url=row.get("url"),
            published_at=published,
            source=row.get("source"),
            snippet=row.get("content") or row.get("snippet"),
        )
        if item:
            out.append(item)
    return _dedupe_search_items(out, limit=num_results)


def _build_external_search_queries(symbols, mode, lookback_days):
    clean_symbols = [str(s or "").strip().upper() for s in (symbols or []) if str(s or "").strip()]
    if not clean_symbols:
        return []
    joined_symbols = " ".join(clean_symbols)
    days = max(1, int(lookback_days or 30))

    if str(mode or "").strip().lower() == "financial":
        return [
            f"{joined_symbols} earnings surprise guidance analyst report last {days} days",
            f"{joined_symbols} quarterly results estimate revision broker commentary last {days} days",
        ]
    return [
        f"{joined_symbols} stock latest news analyst report last {days} days",
        f"{joined_symbols} catalyst risk outlook next 3-6 months last {days} days",
    ]


def _build_external_search_context(symbols, mode, exa_api_key=None, tavily_api_key=None, lookback_days=30):
    exa_key = str(exa_api_key or "").strip()
    tavily_key = str(tavily_api_key or "").strip()
    if not exa_key and not tavily_key:
        return ""

    clean_symbols = []
    seen = set()
    for raw_symbol in symbols or []:
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        clean_symbols.append(symbol)

    if not clean_symbols:
        return ""

    sections = []
    for symbol in clean_symbols:
        queries = _build_external_search_queries(symbols=[symbol], mode=mode, lookback_days=lookback_days)
        if not queries:
            continue

        symbol_items = []
        for query in queries:
            if exa_key:
                symbol_items.extend(
                    _search_with_exa(
                        query,
                        exa_key,
                        max_results=EXTERNAL_SEARCH_ITEMS_PER_STOCK,
                        lookback_days=lookback_days,
                    )
                )

        if tavily_key and len(symbol_items) < EXTERNAL_SEARCH_ITEMS_PER_STOCK:
            for query in queries:
                symbol_items.extend(
                    _search_with_tavily(
                        query,
                        tavily_key,
                        max_results=EXTERNAL_SEARCH_ITEMS_PER_STOCK,
                        lookback_days=lookback_days,
                    )
                )
                if len(symbol_items) >= EXTERNAL_SEARCH_ITEMS_PER_STOCK:
                    break

        merged = _dedupe_search_items(symbol_items, limit=EXTERNAL_SEARCH_ITEMS_PER_STOCK)
        if not merged:
            continue

        section_lines = [f"### {symbol}"]
        for idx, item in enumerate(merged, start=1):
            provider = str(item.get("provider", "")).strip().upper() or "WEB"
            title = str(item.get("title", "")).strip()
            source = str(item.get("source", "")).strip() or "--"
            published = str(item.get("published_at", "")).strip() or "--"
            url = str(item.get("url", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            line = f"{idx}. [{provider}] {title} | {source} | {published} | {url}"
            section_lines.append(line)
            if snippet:
                section_lines.append(f"   摘要: {snippet}")
        sections.append("\n".join(section_lines))

    return "\n\n".join(sections)


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
        _record_fetch_issue(f"finnhub{path}", exc=exc)
        return {}, str(exc)


def _first_valid_number(*values):
    for value in values:
        if _is_number(value):
            return float(value)
    return None


def _to_iso_date_from_epoch(ts):
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
    except Exception:
        return None


def _yahoo_quote_summary(symbol, modules):
    try:
        modules_str = ",".join(modules)
        url = (
            f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
            f"?modules={modules_str}"
        )
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        result = (data.get("quoteSummary") or {}).get("result") or []
        if result and isinstance(result[0], dict):
            return result[0]
    except Exception as exc:
        _record_fetch_issue("yahoo.quote_summary", exc=exc)
    return {}


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
    except Exception as exc:
        _record_fetch_issue("yahoo.chart", exc=exc)
        return [], []


def _finnhub_bundle(symbol, api_key):
    quote, e_quote = _safe_finnhub_get("/quote", {"symbol": symbol}, api_key)
    profile, e_profile = _safe_finnhub_get("/stock/profile2", {"symbol": symbol}, api_key)
    metric_resp, e_metric = _safe_finnhub_get("/stock/metric", {"symbol": symbol, "metric": "all"}, api_key)
    metric = metric_resp.get("metric", {}) if isinstance(metric_resp, dict) else {}
    financials_annual, e_fin_annual = _safe_finnhub_get(
        "/stock/financials-reported", {"symbol": symbol, "freq": "annual"}, api_key
    )
    financials_quarterly, e_fin_quarterly = _safe_finnhub_get(
        "/stock/financials-reported", {"symbol": symbol, "freq": "quarterly"}, api_key
    )
    # 某些 Finnhub 套餐无 candle 权限，降级到 Yahoo chart 用于补齐5日/20日/250日与成交额
    closes, volumes = _yahoo_chart_prices(symbol, range_str="2y", interval="1d")

    return {
        "quote": quote,
        "profile": profile,
        "metric": metric,
        "closes": closes,
        "volumes": volumes,
        # financials 保持兼容旧逻辑（第2部分历史财务展示使用）
        "financials": financials_annual,
        # AI 上下文专用：3Y 年报 + 4Q 季报
        "financials_annual": financials_annual,
        "financials_quarterly": financials_quarterly,
        "errors": {
            "quote": e_quote,
            "profile": e_profile,
            "metric": e_metric,
            "financials_annual": e_fin_annual,
            "financials_quarterly": e_fin_quarterly,
        },
    }


def _parse_yahoo_single_page(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    analysis_eps_trend = None
    if "/analysis/" in str(url or "").lower():
        analysis_eps_trend = _extract_eps_trend_current_estimate_from_soup(soup)

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

    return {
        "display_metrics": display_metrics,
        "quote_summary": quote_summary,
        "analysis_eps_trend": analysis_eps_trend,
    }


def _parse_yahoo_pages(symbol):
    urls = [
        f"https://finance.yahoo.com/quote/{symbol}/",
        f"https://finance.yahoo.com/quote/{symbol}/key-statistics/",
        f"https://finance.yahoo.com/quote/{symbol}/analysis/",
    ]
    merged_metrics = {}
    merged_summary = {}
    merged_analysis_eps_trend = {
        "current_year_eps": None,
        "next_qtr_eps": None,
        "next_year_eps": None,
    }
    for url in urls:
        try:
            res = _parse_yahoo_single_page(url)
            for k, v in (res.get("display_metrics") or {}).items():
                if k not in merged_metrics:
                    merged_metrics[k] = v
            if isinstance(res.get("quote_summary"), dict):
                merged_summary.update(res.get("quote_summary"))
            analysis_eps_trend = (
                res.get("analysis_eps_trend") if isinstance(res.get("analysis_eps_trend"), dict) else {}
            )
            for key in ("current_year_eps", "next_qtr_eps", "next_year_eps"):
                if _is_number(merged_analysis_eps_trend.get(key)):
                    continue
                value = analysis_eps_trend.get(key)
                if _is_number(value):
                    merged_analysis_eps_trend[key] = float(value)
        except Exception as exc:
            _record_fetch_issue(f"yahoo.page:{url}", exc=exc)
            continue
    return {
        "display_metrics": merged_metrics,
        "quote_summary": merged_summary,
        "analysis_eps_trend": merged_analysis_eps_trend,
    }


def _extract_eps_trend_current_estimate_from_soup(soup):
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [x.get_text(" ", strip=True) for x in rows[0].find_all(["th", "td"])]
        if len(headers) < 4:
            continue

        next_qtr_idx = None
        current_year_idx = None
        next_year_idx = None
        for idx, header in enumerate(headers):
            h = (header or "").lower()
            if next_qtr_idx is None and h.startswith("next qtr"):
                next_qtr_idx = idx
            if current_year_idx is None and h.startswith("current year"):
                current_year_idx = idx
            if next_year_idx is None and h.startswith("next year"):
                next_year_idx = idx
        if next_qtr_idx is None or current_year_idx is None:
            continue

        for row in rows[1:]:
            cells = [x.get_text(" ", strip=True) for x in row.find_all(["th", "td"])]
            if not cells:
                continue
            if cells[0].strip().lower() != "current estimate":
                continue

            next_qtr_val = (
                _parse_display_number(cells[next_qtr_idx]) if next_qtr_idx < len(cells) else None
            )
            current_year_val = (
                _parse_display_number(cells[current_year_idx]) if current_year_idx < len(cells) else None
            )
            next_year_val = (
                _parse_display_number(cells[next_year_idx]) if next_year_idx is not None and next_year_idx < len(cells) else None
            )
            return {
                "current_year_eps": current_year_val,
                "next_qtr_eps": next_qtr_val,
                "next_year_eps": next_year_val,
            }

    return {"current_year_eps": None, "next_qtr_eps": None, "next_year_eps": None}


def _extract_eps_trend_current_estimate(symbol):
    url = f"https://finance.yahoo.com/quote/{symbol}/analysis/"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _extract_eps_trend_current_estimate_from_soup(soup)


def _to_float(value):
    if _is_number(value):
        return float(value)
    if value is None:
        return None

    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "N/A", "NA", "nan", "NaN", "None"}:
        return None

    try:
        parsed = float(text)
        return parsed if _is_number(parsed) else None
    except Exception:
        parsed = _parse_display_number(text)
        return float(parsed) if _is_number(parsed) else None


def _to_pct(value):
    number = _to_float(value)
    if not _is_number(number):
        return None
    scaled = float(number) * 100 if abs(float(number)) <= 1.5 else float(number)
    return _round(scaled)


def _normalize_period_token(value):
    return str(value or "").strip().lower().replace(" ", "")


def _fetch_ticker_df(ticker, getter_name, attr_name):
    df = None
    if getter_name and hasattr(ticker, getter_name):
        try:
            candidate = getattr(ticker, getter_name)()
            if isinstance(candidate, pd.DataFrame):
                df = candidate
        except Exception:
            df = None

    if (not isinstance(df, pd.DataFrame) or df.empty) and attr_name:
        candidate = getattr(ticker, attr_name, None)
        if isinstance(candidate, pd.DataFrame):
            df = candidate

    if isinstance(df, pd.DataFrame):
        return df.copy()
    return pd.DataFrame()


def _find_period_row(df, aliases):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None, None

    rows = [(_normalize_period_token(idx), idx) for idx in df.index]
    wanted = [_normalize_period_token(alias) for alias in (aliases or []) if str(alias or "").strip()]

    for key in wanted:
        for token, raw_idx in rows:
            if token == key:
                row = df.loc[raw_idx]
                return str(raw_idx), row if isinstance(row, pd.Series) else None

    for key in wanted:
        if not key:
            continue
        for token, raw_idx in rows:
            if key in token or token in key:
                row = df.loc[raw_idx]
                return str(raw_idx), row if isinstance(row, pd.Series) else None

    return None, None


def _series_value_by_aliases(series, aliases):
    if not isinstance(series, pd.Series):
        return None

    alias_keys = {_normalize_label_key(alias) for alias in (aliases or [])}
    for col, value in series.items():
        if _normalize_label_key(col) in alias_keys:
            parsed = _to_float(value)
            if _is_number(parsed):
                return float(parsed)
    return None


def _safe_iso_date(value):
    if isinstance(value, pd.Timestamp):
        try:
            return value.date().isoformat()
        except Exception:
            return str(value)
    text = str(value or "").strip()
    if not text:
        return None
    iso = _to_iso_date_from_text(text)
    return iso or text


def _empty_expectation_guidance_snapshot():
    beat_conclusion = "信息不足：暂无可用的财报 beat/miss 与历史 EPS surprise 数据。"
    guidance_conclusion = "该模块已下线：不再展示管理层 guidance 与预期修正。"
    trend_conclusion = "信息不足：暂无可用的 EPS Trend（7/30/60/90天）数据。"
    overall = "信息不足：预期与指引模块缺少关键数据，建议结合最新财报公告和卖方报告复核。"
    return {
        "beat_miss": {
            "latest_quarter": None,
            "latest_eps_actual": None,
            "latest_eps_estimate": None,
            "latest_surprise_pct": None,
            "latest_result": "insufficient",
            "beat_count_4q": 0,
            "miss_count_4q": 0,
            "inline_count_4q": 0,
            "beat_streak_4q": 0,
            "avg_surprise_pct_4q": None,
            "history_surprise_pct_4q": [],
            "conclusion": beat_conclusion,
        },
        "guidance": {
            "eps_current_year_avg": None,
            "eps_current_year_low": None,
            "eps_current_year_high": None,
            "eps_next_year_avg": None,
            "eps_next_year_low": None,
            "eps_next_year_high": None,
            "revenue_current_year_avg_b": None,
            "revenue_current_year_low_b": None,
            "revenue_current_year_high_b": None,
            "revenue_next_year_avg_b": None,
            "revenue_next_year_low_b": None,
            "revenue_next_year_high_b": None,
            "revision_period": None,
            "up_last_7d": None,
            "down_last_7d": None,
            "up_last_30d": None,
            "down_last_30d": None,
            "net_revision_30d": None,
            "revision_signal": "insufficient",
            "news_guidance_signal": "insufficient",
            "news_guidance_evidence": None,
            "signal": "insufficient",
            "official_source_count": 0,
            "source_highlights": [],
            "conclusion": guidance_conclusion,
        },
        "eps_trend": {
            "period": None,
            "current": None,
            "d7": None,
            "d30": None,
            "d60": None,
            "d90": None,
            "change_vs_30d_pct": None,
            "change_vs_90d_pct": None,
            "signal": "insufficient",
            "conclusion": trend_conclusion,
        },
        "conclusion": {
            "beat_miss": beat_conclusion,
            "guidance": guidance_conclusion,
            "eps_trend": trend_conclusion,
            "overall": overall,
        },
    }


def _classify_surprise(surprise_pct):
    if not _is_number(surprise_pct):
        return "insufficient"
    if surprise_pct > 0.5:
        return "beat"
    if surprise_pct < -0.5:
        return "miss"
    return "inline"


def _build_beat_miss_snapshot(history_df):
    base = _empty_expectation_guidance_snapshot()["beat_miss"]
    if not isinstance(history_df, pd.DataFrame) or history_df.empty:
        return base

    records = []
    for idx, row in history_df.iterrows():
        if not isinstance(row, pd.Series):
            continue
        actual = _series_value_by_aliases(row, ["epsActual", "eps actual", "reportedEPS", "actual"])
        estimate = _series_value_by_aliases(row, ["epsEstimate", "eps estimate", "estimate"])
        surprise = _series_value_by_aliases(row, ["surprisePercent", "surprise(%)", "surprise %", "surprise"])
        surprise_pct = _to_pct(surprise)
        if surprise_pct is None and _is_number(actual) and _is_number(estimate) and float(estimate) != 0:
            surprise_pct = _pct_change(actual, estimate)

        records.append(
            {
                "quarter": _safe_iso_date(idx),
                "actual": _round(actual),
                "estimate": _round(estimate),
                "surprise_pct": surprise_pct,
            }
        )

    records = [item for item in records if item.get("quarter")]
    if not records:
        return base

    records.sort(key=lambda item: str(item.get("quarter") or ""))
    recent = records[-4:]
    latest = recent[-1]
    surprise_values = [item.get("surprise_pct") for item in recent if _is_number(item.get("surprise_pct"))]

    beat_count = 0
    miss_count = 0
    inline_count = 0
    for value in surprise_values:
        cls = _classify_surprise(value)
        if cls == "beat":
            beat_count += 1
        elif cls == "miss":
            miss_count += 1
        else:
            inline_count += 1

    beat_streak = 0
    for item in reversed(recent):
        if _classify_surprise(item.get("surprise_pct")) == "beat":
            beat_streak += 1
            continue
        break

    latest_result = _classify_surprise(latest.get("surprise_pct"))
    avg_surprise = _round(sum(surprise_values) / len(surprise_values)) if surprise_values else None

    if beat_streak >= 3:
        conclusion = "近4季连续超预期，历史兑现能力强。"
    elif beat_count >= 3 and miss_count == 0:
        conclusion = "近4季以超预期为主，历史表现偏稳健。"
    elif miss_count >= 2 and beat_count <= 1:
        conclusion = "近4季 miss 次数偏多，历史兑现存在压力。"
    elif surprise_values:
        conclusion = "近4季 beat/miss 交替出现，历史表现分化。"
    else:
        conclusion = base.get("conclusion")

    return {
        "latest_quarter": latest.get("quarter"),
        "latest_eps_actual": latest.get("actual"),
        "latest_eps_estimate": latest.get("estimate"),
        "latest_surprise_pct": latest.get("surprise_pct"),
        "latest_result": latest_result,
        "beat_count_4q": beat_count,
        "miss_count_4q": miss_count,
        "inline_count_4q": inline_count,
        "beat_streak_4q": beat_streak,
        "avg_surprise_pct_4q": avg_surprise,
        "history_surprise_pct_4q": [item.get("surprise_pct") for item in recent if _is_number(item.get("surprise_pct"))],
        "conclusion": conclusion,
    }


def _build_eps_trend_snapshot(eps_trend_df):
    base = _empty_expectation_guidance_snapshot()["eps_trend"]

    period, row = _find_period_row(eps_trend_df, ["+1y", "1y", "next year", "nexty", "0y", "current year", "curry"])
    if row is None:
        period, row = _find_period_row(eps_trend_df, ["+1q", "1q", "next qtr", "next quarter", "0q"])
    if row is None:
        return base

    current = _round(_series_value_by_aliases(row, ["current"]))
    d7 = _round(_series_value_by_aliases(row, ["7daysAgo", "7 days ago", "7d"]))
    d30 = _round(_series_value_by_aliases(row, ["30daysAgo", "30 days ago", "30d"]))
    d60 = _round(_series_value_by_aliases(row, ["60daysAgo", "60 days ago", "60d"]))
    d90 = _round(_series_value_by_aliases(row, ["90daysAgo", "90 days ago", "90d"]))

    change_30 = _pct_change(current, d30) if _is_number(current) and _is_number(d30) and d30 != 0 else None
    change_90 = _pct_change(current, d90) if _is_number(current) and _is_number(d90) and d90 != 0 else None
    driver_change = change_90 if _is_number(change_90) else change_30

    if not _is_number(driver_change):
        signal = "insufficient"
        conclusion = base.get("conclusion")
    elif driver_change >= 8:
        signal = "up"
        conclusion = "EPS Trend 显示近90天一致预期明显上修。"
    elif driver_change >= 3:
        signal = "up"
        conclusion = "EPS Trend 显示一致预期温和上修。"
    elif driver_change <= -8:
        signal = "down"
        conclusion = "EPS Trend 显示近90天一致预期明显下修。"
    elif driver_change <= -3:
        signal = "down"
        conclusion = "EPS Trend 显示一致预期温和下修。"
    else:
        signal = "flat"
        conclusion = "EPS Trend 显示一致预期整体平稳。"

    return {
        "period": period,
        "current": current,
        "d7": d7,
        "d30": d30,
        "d60": d60,
        "d90": d90,
        "change_vs_30d_pct": change_30,
        "change_vs_90d_pct": change_90,
        "signal": signal,
        "conclusion": conclusion,
    }


def _build_expectation_overall_conclusion(beat_miss, guidance, eps_trend):
    score = 0
    has_signal = False

    beat_result = str((beat_miss or {}).get("latest_result") or "").lower()
    if beat_result == "beat":
        score += 1
        has_signal = True
    elif beat_result == "miss":
        score -= 1
        has_signal = True

    beat_streak = int((beat_miss or {}).get("beat_streak_4q") or 0)
    miss_count = int((beat_miss or {}).get("miss_count_4q") or 0)
    if beat_streak >= 3:
        score += 1
        has_signal = True
    elif miss_count >= 2:
        score -= 1
        has_signal = True

    trend_signal = str((eps_trend or {}).get("signal") or "").lower()
    if trend_signal == "up":
        score += 1
        has_signal = True
    elif trend_signal == "down":
        score -= 1
        has_signal = True

    if not has_signal:
        return "信息不足：预期与指引证据不完整，暂不形成方向性判断。"
    if score >= 2:
        return "综合结论：预期与指引信号偏积极，基本面预期处于上修区间。"
    if score <= -2:
        return "综合结论：预期与指引信号偏谨慎，基本面预期存在下修压力。"
    return "综合结论：预期与指引信号分化，建议继续跟踪下一次财报与指引更新。"


def _build_expectation_guidance_snapshot(
    symbol,
    news=None,
):
    snapshot = _empty_expectation_guidance_snapshot()
    earnings_history_df = pd.DataFrame()
    eps_trend_df = pd.DataFrame()

    if yf is not None:
        try:
            ticker = yf.Ticker(symbol)
        except Exception:
            ticker = None
        if ticker is not None:
            earnings_history_df = _fetch_ticker_df(ticker, "get_earnings_history", "earnings_history")
            eps_trend_df = _fetch_ticker_df(ticker, "get_eps_trend", "eps_trend")

    beat_miss = _build_beat_miss_snapshot(earnings_history_df)
    # Guidance/预期修正模块按产品要求已下线，保留空结构仅用于兼容前端字段。
    guidance = snapshot.get("guidance", {})
    eps_trend = _build_eps_trend_snapshot(eps_trend_df)
    overall = _build_expectation_overall_conclusion(beat_miss, guidance, eps_trend)

    snapshot["beat_miss"] = beat_miss
    snapshot["guidance"] = guidance
    snapshot["eps_trend"] = eps_trend
    snapshot["conclusion"] = {
        "beat_miss": beat_miss.get("conclusion"),
        "guidance": guidance.get("conclusion"),
        "eps_trend": eps_trend.get("conclusion"),
        "overall": overall,
    }
    return snapshot


def _to_bounded_pct(numerator, denominator):
    if not _is_number(numerator) or not _is_number(denominator) or float(denominator) == 0:
        return None
    return _round((float(numerator) / float(denominator)) * 100)


def _empty_financial_snapshot():
    return {
        "currency": None,
        "latest_period": None,
        "latest_report_date": None,
        "latest_period_type": None,
        "revenue_b": None,
        "revenue_yoy_pct": None,
        "net_income_b": None,
        "net_income_yoy_pct": None,
        "eps": None,
        "gross_margin_pct": None,
        "operating_margin_pct": None,
        "roe_pct": None,
        "net_margin_pct": None,
    }


def _normalize_label_key(label):
    return re.sub(r"[^a-z0-9]+", "", str(label or "").lower())


def _statement_columns_sorted(df):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    parsed = []
    for col in df.columns:
        try:
            parsed.append((pd.Timestamp(col), col))
        except Exception:
            continue
    if not parsed:
        return list(df.columns)
    parsed.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in parsed]


def _find_same_period_last_year(columns, latest_col):
    if not columns or latest_col is None:
        return None
    try:
        latest_ts = pd.Timestamp(latest_col)
    except Exception:
        return columns[4] if len(columns) >= 5 else None

    candidates = []
    for col in columns[1:]:
        try:
            ts = pd.Timestamp(col)
        except Exception:
            continue
        delta_days = (latest_ts - ts).days
        if 250 <= delta_days <= 500:
            candidates.append((abs(delta_days - 365), delta_days, col))
    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[0][2]

    return columns[4] if len(columns) >= 5 else None


def _extract_income_stmt_value(df, column, aliases):
    if not isinstance(df, pd.DataFrame) or df.empty or column is None:
        return None
    if column not in df.columns:
        return None

    row_map = {}
    for idx in df.index:
        key = _normalize_label_key(idx)
        if key and key not in row_map:
            row_map[key] = idx

    for alias in aliases:
        idx = row_map.get(_normalize_label_key(alias))
        if idx is None:
            continue
        value = df.at[idx, column]
        if _is_number(value):
            return float(value)
        try:
            v = float(value)
            if _is_number(v):
                return v
        except Exception:
            continue
    return None


def _to_iso_date_from_value(value):
    try:
        return pd.Timestamp(value).date().isoformat()
    except Exception:
        return None


def _normalize_shares_for_eps(shares, net_income):
    if not _is_number(shares):
        return None
    s = float(shares)
    if s <= 0:
        return None
    if s < 1_000_000 and _is_number(net_income) and abs(float(net_income)) >= 100_000_000:
        # 某些源会用“百万股”为单位，做保守换算。
        return s * 1_000_000
    return s


def _extract_eps_from_income_stmt(df, latest_col):
    eps_aliases = ["Diluted EPS", "DilutedEPS", "Basic EPS", "BasicEPS", "Earnings Per Share Diluted"]
    eps = _extract_income_stmt_value(df, latest_col, eps_aliases)
    if _is_number(eps):
        return float(eps)

    diluted_ni_aliases = [
        "Diluted NI Availto Com Stockholders",
        "Diluted NI Available To Com Stockholders",
        "Diluted NI Avail To Com Stockholders",
        "Net Income Common Stockholders",
        "Net Income",
    ]
    diluted_shares_aliases = [
        "Diluted Average Shares",
        "DilutedAverageShares",
        "Weighted Average Shares Diluted",
        "Diluted Shares Outstanding",
    ]
    basic_ni_aliases = ["Net Income Common Stockholders", "Net Income"]
    basic_shares_aliases = [
        "Basic Average Shares",
        "BasicAverageShares",
        "Weighted Average Shares",
        "Basic Shares Outstanding",
    ]

    diluted_ni = _extract_income_stmt_value(df, latest_col, diluted_ni_aliases)
    diluted_shares = _normalize_shares_for_eps(
        _extract_income_stmt_value(df, latest_col, diluted_shares_aliases), diluted_ni
    )
    if _is_number(diluted_ni) and _is_number(diluted_shares) and float(diluted_shares) != 0:
        return float(diluted_ni) / float(diluted_shares)

    basic_ni = _extract_income_stmt_value(df, latest_col, basic_ni_aliases)
    basic_shares = _normalize_shares_for_eps(
        _extract_income_stmt_value(df, latest_col, basic_shares_aliases), basic_ni
    )
    if _is_number(basic_ni) and _is_number(basic_shares) and float(basic_shares) != 0:
        return float(basic_ni) / float(basic_shares)
    return None


def _extract_eps_from_shares_outstanding(ticker, net_income):
    if not _is_number(net_income):
        return None
    shares = None

    try:
        fast_info = getattr(ticker, "fast_info", None)
        if hasattr(fast_info, "get"):
            shares = fast_info.get("shares")
    except Exception:
        shares = None

    if not _is_number(shares):
        try:
            info = getattr(ticker, "info", None)
            if isinstance(info, dict):
                shares = info.get("sharesOutstanding")
        except Exception:
            shares = None

    shares = _normalize_shares_for_eps(shares, net_income)
    if _is_number(shares) and float(shares) != 0:
        return float(net_income) / float(shares)
    return None


def _extract_eps_from_earnings_dates(ticker, latest_period_iso):
    try:
        df = ticker.get_earnings_dates(limit=12)
    except Exception:
        return None

    if not isinstance(df, pd.DataFrame) or df.empty:
        return None

    eps_col = None
    for col in df.columns:
        c = str(col).strip().lower()
        if "reported" in c and "eps" in c:
            eps_col = col
            break
    if eps_col is None:
        return None

    latest_date = None
    if latest_period_iso:
        try:
            latest_date = pd.Timestamp(latest_period_iso)
        except Exception:
            latest_date = None

    candidates = []
    for idx, row in df.iterrows():
        value = row.get(eps_col)
        if not _is_number(value):
            continue
        try:
            earnings_ts = pd.Timestamp(idx)
        except Exception:
            earnings_ts = None
        if latest_date is None or earnings_ts is None:
            candidates.append((1, 999999, float(value)))
            continue

        delta_days = (earnings_ts - latest_date).days
        preferred = 0 if -120 <= delta_days <= 180 else 1
        candidates.append((preferred, abs(delta_days), float(value)))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][2]


def _extract_latest_report_date_from_earnings_dates(ticker, latest_period_iso):
    try:
        df = ticker.get_earnings_dates(limit=12)
    except Exception:
        return None

    if not isinstance(df, pd.DataFrame) or df.empty:
        return None

    try:
        latest_period = pd.Timestamp(latest_period_iso) if latest_period_iso else None
    except Exception:
        latest_period = None

    candidates = []
    for idx in df.index:
        try:
            ts = pd.Timestamp(idx)
        except Exception:
            continue
        if latest_period is None:
            candidates.append((1, 999999, ts))
            continue

        delta_days = (ts - latest_period).days
        # 财报公布日通常晚于财报期结束日，优先取最近的非负差值。
        preferred = 0 if 0 <= delta_days <= 200 else 1
        candidates.append((preferred, abs(delta_days), ts))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]))
    try:
        return candidates[0][2].date().isoformat()
    except Exception:
        return None


def _build_financial_from_income_stmt(df, period_type, return_latest_col=False):
    result = _empty_financial_snapshot()
    result["latest_period_type"] = period_type

    columns = _statement_columns_sorted(df)
    if not columns:
        return (result, None) if return_latest_col else result

    revenue_aliases = ["Total Revenue", "TotalRevenue", "Revenue"]
    gross_profit_aliases = ["Gross Profit", "GrossProfit"]
    operating_income_aliases = ["Operating Income", "OperatingIncome", "Income From Operations"]
    net_income_aliases = [
        "Net Income",
        "NetIncome",
        "Net Income Common Stockholders",
        "Net Income Including Noncontrolling Interests",
    ]
    eps_aliases = ["Diluted EPS", "DilutedEPS", "Basic EPS", "BasicEPS", "Earnings Per Share Diluted"]

    # 某些股票（如 TER）最新季度会出现 EPS 有值、但收入和利润主字段为 NaN。
    # 这时回退到最近一个“核心财务字段可用”的季度，避免第2部分几乎全是 "--"。
    latest_col = columns[0]
    for candidate_col in columns:
        revenue_candidate = _extract_income_stmt_value(df, candidate_col, revenue_aliases)
        gross_candidate = _extract_income_stmt_value(df, candidate_col, gross_profit_aliases)
        operating_candidate = _extract_income_stmt_value(df, candidate_col, operating_income_aliases)
        net_income_candidate = _extract_income_stmt_value(df, candidate_col, net_income_aliases)
        if any(_is_number(v) for v in (revenue_candidate, gross_candidate, operating_candidate, net_income_candidate)):
            latest_col = candidate_col
            break

    if period_type == "quarterly":
        prev_col = _find_same_period_last_year(columns, latest_col)
    else:
        prev_col = columns[1] if len(columns) >= 2 else None

    revenue_latest = _extract_income_stmt_value(df, latest_col, revenue_aliases)
    revenue_prev = _extract_income_stmt_value(df, prev_col, revenue_aliases)
    gross_profit_latest = _extract_income_stmt_value(df, latest_col, gross_profit_aliases)
    operating_income_latest = _extract_income_stmt_value(df, latest_col, operating_income_aliases)
    net_income_latest = _extract_income_stmt_value(df, latest_col, net_income_aliases)
    net_income_prev = _extract_income_stmt_value(df, prev_col, net_income_aliases)
    eps_latest = _extract_income_stmt_value(df, latest_col, eps_aliases)

    result.update(
        {
            "latest_period": _to_iso_date_from_value(latest_col),
            "revenue_b": _to_billions(revenue_latest),
            "revenue_yoy_pct": _pct_change(revenue_latest, revenue_prev),
            "net_income_b": _to_billions(net_income_latest),
            "net_income_yoy_pct": _pct_change(net_income_latest, net_income_prev),
            "eps": _round(eps_latest),
            "gross_margin_pct": _to_bounded_pct(gross_profit_latest, revenue_latest),
            "operating_margin_pct": _to_bounded_pct(operating_income_latest, revenue_latest),
            "net_margin_pct": _to_bounded_pct(net_income_latest, revenue_latest),
        }
    )
    return (result, latest_col) if return_latest_col else result


def _extract_shareholders_equity_from_balance_frame(balance_df, preferred_col=None):
    if not isinstance(balance_df, pd.DataFrame) or balance_df.empty:
        return None

    equity_aliases = [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Total Stockholder Equity",
        "Common Stock Equity",
    ]

    ordered_cols = _statement_columns_sorted(balance_df)
    candidate_cols = []
    if preferred_col is not None:
        candidate_cols.append(preferred_col)
        preferred_iso = _to_iso_date_from_value(preferred_col)
        if preferred_iso:
            for col in ordered_cols:
                if _to_iso_date_from_value(col) == preferred_iso and col not in candidate_cols:
                    candidate_cols.append(col)
                    break
    candidate_cols.extend([col for col in ordered_cols if col not in candidate_cols])

    for col in candidate_cols:
        equity = _extract_income_stmt_value(balance_df, col, equity_aliases)
        if _is_number(equity):
            return float(equity)
    return None


def _extract_info_roe_pct(info):
    if not isinstance(info, dict):
        return None
    value = _first_valid_number(info.get("returnOnEquity"), info.get("returnOnEquityTTM"))
    if not _is_number(value):
        return None
    roe = float(value)
    # yfinance 常见为小数（如 0.32 表示 32%）；若明显是小数则转成百分比口径。
    if abs(roe) <= 1.5:
        roe *= 100.0
    return _round(roe)


def _compute_roe_pct_from_financials(net_income_b, balance_df, preferred_col=None, info_roe_pct=None):
    net_income = float(net_income_b) * 1_000_000_000 if _is_number(net_income_b) else None
    equity = _extract_shareholders_equity_from_balance_frame(balance_df, preferred_col=preferred_col)
    roe = _to_bounded_pct(net_income, equity)
    if _is_number(roe):
        return roe
    return _round(info_roe_pct) if _is_number(info_roe_pct) else None


def _get_financial_from_yfinance(symbol):
    result = _empty_financial_snapshot()
    if yf is None:
        return result

    try:
        ticker = yf.Ticker(symbol)
        info = getattr(ticker, "info", None)
        info = info if isinstance(info, dict) else {}
        financial_currency = _normalize_currency_code(
            _mapping_get_text(info, "financialCurrency", "currency")
        )
        fallback_roe_pct = _extract_info_roe_pct(info)

        quarterly_balance = _pick_statement_frame(
            getattr(ticker, "quarterly_balance_sheet", None),
            getattr(ticker, "quarterly_balancesheet", None),
        )
        annual_balance = _pick_statement_frame(
            getattr(ticker, "balance_sheet", None),
            getattr(ticker, "balancesheet", None),
        )

        quarterly = getattr(ticker, "quarterly_income_stmt", None)
        if not isinstance(quarterly, pd.DataFrame) or quarterly.empty:
            quarterly = getattr(ticker, "quarterly_financials", None)

        if isinstance(quarterly, pd.DataFrame) and not quarterly.empty:
            result, latest_col = _build_financial_from_income_stmt(
                quarterly, period_type="quarterly", return_latest_col=True
            )
            if result.get("eps") is None:
                eps = _extract_eps_from_income_stmt(quarterly, latest_col)
                if eps is None:
                    net_income = (
                        float(result.get("net_income_b")) * 1_000_000_000
                        if _is_number(result.get("net_income_b"))
                        else None
                    )
                    eps = _extract_eps_from_shares_outstanding(ticker, net_income)
                if eps is None:
                    eps = _extract_eps_from_earnings_dates(ticker, result.get("latest_period"))
                result["eps"] = _round(eps)
            result["roe_pct"] = _compute_roe_pct_from_financials(
                result.get("net_income_b"),
                quarterly_balance,
                preferred_col=latest_col,
                info_roe_pct=fallback_roe_pct,
            )
            result["latest_report_date"] = _extract_latest_report_date_from_earnings_dates(
                ticker,
                result.get("latest_period"),
            )
            if not result.get("latest_report_date"):
                result["latest_report_date"] = result.get("latest_period")
            result["currency"] = financial_currency
            return result

        annual = getattr(ticker, "income_stmt", None)
        if not isinstance(annual, pd.DataFrame) or annual.empty:
            annual = getattr(ticker, "financials", None)
        if isinstance(annual, pd.DataFrame) and not annual.empty:
            result, latest_col = _build_financial_from_income_stmt(
                annual, period_type="annual", return_latest_col=True
            )
            if result.get("eps") is None:
                eps = _extract_eps_from_income_stmt(annual, latest_col)
                if eps is None:
                    net_income = (
                        float(result.get("net_income_b")) * 1_000_000_000
                        if _is_number(result.get("net_income_b"))
                        else None
                    )
                    eps = _extract_eps_from_shares_outstanding(ticker, net_income)
                if eps is None:
                    eps = _extract_eps_from_earnings_dates(ticker, result.get("latest_period"))
                result["eps"] = _round(eps)
            result["roe_pct"] = _compute_roe_pct_from_financials(
                result.get("net_income_b"),
                annual_balance,
                preferred_col=latest_col,
                info_roe_pct=fallback_roe_pct,
            )
            result["latest_report_date"] = _extract_latest_report_date_from_earnings_dates(
                ticker,
                result.get("latest_period"),
            )
            if not result.get("latest_report_date"):
                result["latest_report_date"] = result.get("latest_period")
            result["currency"] = financial_currency
            return result
        result["currency"] = financial_currency
    except Exception:
        return result

    return result


def _pick_statement_frame(*frames):
    for frame in frames:
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            return frame
    return pd.DataFrame()


def _statement_columns_for_context(primary_df, *fallback_dfs):
    columns = _statement_columns_sorted(primary_df)
    if columns:
        return columns
    for df in fallback_dfs:
        columns = _statement_columns_sorted(df)
        if columns:
            return columns
    return []


def _fiscal_period_from_col(col):
    try:
        ts = pd.Timestamp(col)
    except Exception:
        return None, None
    fiscal_year = int(ts.year)
    fiscal_quarter = int(((int(ts.month) - 1) // 3) + 1)
    return fiscal_year, fiscal_quarter


def _build_context_rows_from_yfinance_frames(income_df, cashflow_df, balance_df, period_type, limit):
    if not isinstance(limit, int) or limit <= 0:
        return []

    columns = _statement_columns_for_context(income_df, cashflow_df, balance_df)
    if not columns:
        return []

    revenue_aliases = ["Total Revenue", "TotalRevenue", "Revenue"]
    gross_profit_aliases = ["Gross Profit", "GrossProfit"]
    operating_income_aliases = ["Operating Income", "OperatingIncome", "Income From Operations"]
    net_income_aliases = [
        "Net Income",
        "NetIncome",
        "Net Income Common Stockholders",
        "Net Income Including Noncontrolling Interests",
    ]
    eps_diluted_aliases = ["Diluted EPS", "DilutedEPS", "Earnings Per Share Diluted"]
    eps_basic_aliases = ["Basic EPS", "BasicEPS", "Earnings Per Share Basic"]
    ocf_aliases = [
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
        "Net Cash Provided By Operating Activities",
        "NetCashProvidedByUsedInOperatingActivities",
    ]
    capex_aliases = [
        "Capital Expenditure",
        "Capital Expenditures",
        "Purchase Of PPE",
        "Payments To Acquire Property Plant And Equipment",
    ]
    total_assets_aliases = ["Total Assets"]
    total_liabilities_aliases = ["Total Liabilities Net Minority Interest", "Total Liabilities"]
    equity_aliases = [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Total Stockholder Equity",
        "Common Stock Equity",
    ]

    rows = []
    for col in columns[:limit]:
        revenue = _extract_income_stmt_value(income_df, col, revenue_aliases)
        gross_profit = _extract_income_stmt_value(income_df, col, gross_profit_aliases)
        operating_income = _extract_income_stmt_value(income_df, col, operating_income_aliases)
        net_income = _extract_income_stmt_value(income_df, col, net_income_aliases)
        eps_diluted = _extract_income_stmt_value(income_df, col, eps_diluted_aliases)
        eps_basic = _extract_income_stmt_value(income_df, col, eps_basic_aliases)
        if not _is_number(eps_diluted):
            eps_diluted = _extract_eps_from_income_stmt(income_df, col)
        if not _is_number(eps_basic) and _is_number(eps_diluted):
            eps_basic = eps_diluted

        operating_cash_flow = _extract_income_stmt_value(cashflow_df, col, ocf_aliases)
        capex = _extract_income_stmt_value(cashflow_df, col, capex_aliases)
        free_cash_flow = None
        if _is_number(operating_cash_flow) and _is_number(capex):
            free_cash_flow = float(operating_cash_flow) + float(capex)

        total_assets = _extract_income_stmt_value(balance_df, col, total_assets_aliases)
        total_liabilities = _extract_income_stmt_value(balance_df, col, total_liabilities_aliases)
        shareholders_equity = _extract_income_stmt_value(balance_df, col, equity_aliases)

        fiscal_year, fiscal_quarter = _fiscal_period_from_col(col)
        rows.append(
            {
                "period_end": _to_iso_date_from_value(col),
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter if period_type == "quarterly" else None,
                "filed_date": None,
                "revenue_b": _to_billions(revenue),
                "gross_profit_b": _to_billions(gross_profit),
                "operating_income_b": _to_billions(operating_income),
                "net_income_b": _to_billions(net_income),
                "gross_margin_pct": _to_bounded_pct(gross_profit, revenue),
                "operating_margin_pct": _to_bounded_pct(operating_income, revenue),
                "net_margin_pct": _to_bounded_pct(net_income, revenue),
                "eps_diluted": _round(eps_diluted),
                "eps_basic": _round(eps_basic),
                "operating_cash_flow_b": _to_billions(operating_cash_flow),
                "capex_b": _to_billions(capex),
                "free_cash_flow_b": _to_billions(free_cash_flow),
                "total_assets_b": _to_billions(total_assets),
                "total_liabilities_b": _to_billions(total_liabilities),
                "shareholders_equity_b": _to_billions(shareholders_equity),
            }
        )

    return rows


def _build_ai_financial_context_from_yfinance(symbol, annual_limit=3, quarterly_limit=4):
    if yf is None:
        return {"annual": [], "quarterly": []}

    try:
        ticker = yf.Ticker(symbol)

        annual_income = _pick_statement_frame(
            getattr(ticker, "income_stmt", None),
            getattr(ticker, "financials", None),
        )
        quarterly_income = _pick_statement_frame(
            getattr(ticker, "quarterly_income_stmt", None),
            getattr(ticker, "quarterly_financials", None),
        )

        annual_cashflow = _pick_statement_frame(
            getattr(ticker, "cashflow", None),
            getattr(ticker, "cash_flow", None),
        )
        quarterly_cashflow = _pick_statement_frame(
            getattr(ticker, "quarterly_cashflow", None),
            getattr(ticker, "quarterly_cash_flow", None),
        )

        annual_balance = _pick_statement_frame(
            getattr(ticker, "balance_sheet", None),
            getattr(ticker, "balancesheet", None),
        )
        quarterly_balance = _pick_statement_frame(
            getattr(ticker, "quarterly_balance_sheet", None),
            getattr(ticker, "quarterly_balancesheet", None),
        )

        return {
            "annual": _build_context_rows_from_yfinance_frames(
                annual_income, annual_cashflow, annual_balance, "annual", annual_limit
            ),
            "quarterly": _build_context_rows_from_yfinance_frames(
                quarterly_income, quarterly_cashflow, quarterly_balance, "quarterly", quarterly_limit
            ),
        }
    except Exception:
        return {"annual": [], "quarterly": []}


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
    c250 = _pct_change(valid_closes[-1], valid_closes[-251]) if len(valid_closes) >= 251 else None

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
    quote_currency = _normalize_currency_code(profile.get("currency"))
    stock_name = _mapping_get_text(profile, "name", "ticker")
    trade_date = _to_iso_date_from_epoch(quote.get("t"))

    return {
        "stock_name": stock_name,
        "trade_date": trade_date,
        "currency": quote_currency,
        "price": _round(price),
        "change_pct": _round(change_pct),
        "market_cap_b": market_cap_b,
        "turnover_b": turnover_b,
        "pe_ttm": _round(pe_ttm),
        "change_5d_pct": c5,
        "change_20d_pct": c20,
        "change_250d_pct": c250,
    }


def _mapping_get_number(mapping, *keys):
    if not hasattr(mapping, "get"):
        return None
    for key in keys:
        try:
            value = mapping.get(key)
        except Exception:
            value = None
        if _is_number(value):
            return float(value)
    return None


def _mapping_get_text(mapping, *keys):
    if not hasattr(mapping, "get"):
        return None
    for key in keys:
        try:
            value = mapping.get(key)
        except Exception:
            value = None
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _to_float_list(values):
    out = []
    if values is None:
        return out
    for value in values:
        try:
            num = float(value)
        except Exception:
            continue
        if math.isnan(num):
            continue
        out.append(num)
    return out


def _yfinance_history_prices(ticker):
    try:
        hist = ticker.history(period="2y", interval="1d", auto_adjust=False)
    except Exception:
        return [], []

    if not isinstance(hist, pd.DataFrame) or hist.empty:
        return [], []

    close_series = hist["Close"] if "Close" in hist else []
    volume_series = hist["Volume"] if "Volume" in hist else []
    close_values = close_series.tolist() if hasattr(close_series, "tolist") else close_series
    volume_values = volume_series.tolist() if hasattr(volume_series, "tolist") else volume_series
    return _to_float_list(close_values), _to_float_list(volume_values)


def _get_realtime_from_yfinance(symbol):
    empty = {
        "stock_name": None,
        "trade_date": None,
        "currency": None,
        "price": None,
        "change_pct": None,
        "market_cap_b": None,
        "turnover_b": None,
        "pe_ttm": None,
        "change_5d_pct": None,
        "change_20d_pct": None,
        "change_250d_pct": None,
    }
    if yf is None:
        return empty

    try:
        ticker = yf.Ticker(symbol)
    except Exception:
        return empty

    info = getattr(ticker, "info", None)
    info = info if isinstance(info, dict) else {}
    fast_info = getattr(ticker, "fast_info", None)

    # 优先使用 regular market 口径，避免 fast_info.previousClose 偶发与昨收不一致导致涨跌幅偏差。
    price = _first_valid_number(
        _mapping_get_number(info, "regularMarketPrice", "currentPrice"),
        _mapping_get_number(fast_info, "regularMarketPrice", "currentPrice"),
        _mapping_get_number(fast_info, "lastPrice", "last_price"),
    )
    prev_close = _first_valid_number(
        _mapping_get_number(info, "regularMarketPreviousClose", "previousClose"),
        _mapping_get_number(fast_info, "regularMarketPreviousClose", "previousClose", "previous_close"),
    )
    market_cap = _first_valid_number(
        _mapping_get_number(fast_info, "marketCap", "market_cap"),
        _mapping_get_number(info, "marketCap"),
    )
    pe_ttm = _first_valid_number(
        _mapping_get_number(fast_info, "trailingPE", "trailing_pe"),
        _mapping_get_number(info, "trailingPE"),
    )
    quote_currency = _normalize_currency_code(
        _mapping_get_text(info, "currency")
        or _mapping_get_text(fast_info, "currency")
        or _mapping_get_text(info, "financialCurrency")
    )
    stock_name = _mapping_get_text(info, "shortName", "longName", "displayName", "symbol")
    trade_date = _to_iso_date_from_epoch(
        _first_valid_number(
            _mapping_get_number(info, "regularMarketTime", "postMarketTime", "preMarketTime"),
            _mapping_get_number(fast_info, "lastTradeTime", "last_trade_time"),
        )
    )

    closes, volumes = _yfinance_history_prices(ticker)
    if not closes:
        closes, volumes = _yahoo_chart_prices(symbol, range_str="2y", interval="1d")
    valid_closes = [float(x) for x in closes if _is_number(x)]
    valid_volumes = [float(x) for x in volumes if _is_number(x)]

    if not _is_number(price) and valid_closes:
        price = valid_closes[-1]
    if not _is_number(prev_close) and len(valid_closes) >= 2:
        prev_close = valid_closes[-2]

    c5 = _pct_change(valid_closes[-1], valid_closes[-6]) if len(valid_closes) >= 6 else None
    c20 = _pct_change(valid_closes[-1], valid_closes[-21]) if len(valid_closes) >= 21 else None
    c250 = _pct_change(valid_closes[-1], valid_closes[-251]) if len(valid_closes) >= 251 else None

    turnover_b = None
    if valid_closes and valid_volumes:
        turnover_b = _to_billions(float(valid_closes[-1]) * float(valid_volumes[-1]))
    if trade_date is None:
        try:
            recent_hist = ticker.history(period="7d", interval="1d", auto_adjust=False)
        except Exception:
            recent_hist = None
        if isinstance(recent_hist, pd.DataFrame) and not recent_hist.empty:
            trade_date = _safe_iso_date(recent_hist.index[-1])

    return {
        "stock_name": stock_name,
        "trade_date": trade_date,
        "currency": quote_currency,
        "price": _round(price),
        "change_pct": _pct_change(price, prev_close),
        "market_cap_b": _to_billions(market_cap),
        "turnover_b": turnover_b,
        "pe_ttm": _round(pe_ttm),
        "change_5d_pct": c5,
        "change_20d_pct": c20,
        "change_250d_pct": c250,
    }


def _merge_realtime_snapshot(primary, fallback):
    merged = dict(primary or {})
    for key, value in (fallback or {}).items():
        if merged.get(key) is None:
            merged[key] = value
    return merged


def _attach_currency_snapshot(symbol, realtime, financial, forecast, finnhub_bundle=None):
    profile = finnhub_bundle.get("profile", {}) if isinstance(finnhub_bundle, dict) else {}
    inferred = _infer_currency_from_symbol(symbol)

    quote_currency = _normalize_currency_code((realtime or {}).get("currency"))
    if not quote_currency and isinstance(profile, dict):
        quote_currency = _normalize_currency_code(profile.get("currency"))

    financial_currency = _normalize_currency_code((financial or {}).get("currency"))
    raw_forecast_currency = _normalize_currency_code((forecast or {}).get("currency"))

    if not quote_currency:
        quote_currency = financial_currency or raw_forecast_currency or inferred
    if not financial_currency:
        financial_currency = quote_currency or raw_forecast_currency or inferred
    forecast_currency = financial_currency or quote_currency or raw_forecast_currency or inferred

    if isinstance(realtime, dict):
        realtime["currency"] = quote_currency
    if isinstance(financial, dict):
        financial["currency"] = financial_currency
    if isinstance(forecast, dict):
        forecast["currency"] = forecast_currency

    return {
        "quote": quote_currency,
        "financial": financial_currency,
        "forecast": forecast_currency,
    }


def _to_iso_date_from_text(text):
    if not text:
        return None
    v = str(text).strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except Exception:
            continue
    return None


def _extract_next_quarter_eps(qs):
    trend = _extract_raw(qs, ["earningsTrend", "trend"])
    if not isinstance(trend, list):
        return None

    def _period(item):
        return str((item or {}).get("period") or "").strip().lower().replace(" ", "")

    for item in trend:
        if _period(item) in {"+1q", "1q", "nextquarter", "nextq"}:
            eps = _extract_raw(item, ["epsEstimate"])
            if _is_number(eps):
                return float(eps)

    for item in trend:
        p = _period(item)
        if "q" in p and p not in {"0q", "+0q", "currentq", "currq"}:
            eps = _extract_raw(item, ["epsEstimate"])
            if _is_number(eps):
                return float(eps)

    return None


def _extract_next_year_eps(qs):
    trend = _extract_raw(qs, ["earningsTrend", "trend"])
    if not isinstance(trend, list):
        return None

    def _period(item):
        return str((item or {}).get("period") or "").strip().lower().replace(" ", "")

    for item in trend:
        if _period(item) in {"+1y", "1y", "nextyear", "nexty"}:
            eps = _extract_raw(item, ["epsEstimate"])
            if _is_number(eps):
                return float(eps)

    for item in trend:
        p = _period(item)
        if "y" in p and "q" not in p and p not in {"0y", "+0y", "currentyear", "curryear", "curry"}:
            eps = _extract_raw(item, ["epsEstimate"])
            if _is_number(eps):
                return float(eps)

    return None


def _pick_eps_from_yfinance_frame(df, preferred_tokens=None, fallback_predicate=None, candidate_cols=None):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None

    preferred = {str(token or "").strip().lower() for token in (preferred_tokens or []) if str(token or "").strip()}
    col_map = {str(col).strip().lower(): col for col in df.columns}
    selected_cols = []
    for col in candidate_cols or []:
        key = str(col).strip().lower()
        actual = col_map.get(key)
        if actual is not None and actual not in selected_cols:
            selected_cols.append(actual)
    if not selected_cols:
        selected_cols = list(df.columns)

    rows = [(_normalize_period_token(idx), idx) for idx in df.index]

    def _scan(matcher):
        for token, original_idx in rows:
            if not matcher(token):
                continue
            for col in selected_cols:
                value = _to_float(df.at[original_idx, col])
                if _is_number(value):
                    return float(value)
        return None

    if preferred:
        value = _scan(lambda token: token in preferred)
        if value is not None:
            return value
    if callable(fallback_predicate):
        return _scan(lambda token: bool(fallback_predicate(token)))
    return None


def _collect_datetime_candidates(value, out):
    if value is None:
        return

    if isinstance(value, pd.DataFrame):
        _collect_datetime_candidates(value.to_numpy().flatten().tolist(), out)
        return
    if isinstance(value, pd.Series):
        _collect_datetime_candidates(value.tolist(), out)
        return
    if isinstance(value, dict):
        _collect_datetime_candidates(list(value.values()), out)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_datetime_candidates(item, out)
        return

    try:
        ts = pd.Timestamp(value)
    except Exception:
        return
    if pd.isna(ts):
        return
    try:
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
    except Exception:
        return
    out.append(ts)


def _extract_next_earnings_date_from_yfinance_ticker(ticker):
    candidates = []

    try:
        earnings_df = ticker.get_earnings_dates(limit=12)
    except Exception:
        earnings_df = None
    if isinstance(earnings_df, pd.DataFrame) and not earnings_df.empty:
        _collect_datetime_candidates(list(earnings_df.index), candidates)

    try:
        _collect_datetime_candidates(getattr(ticker, "calendar", None), candidates)
    except Exception:
        pass

    try:
        get_calendar = getattr(ticker, "get_calendar", None)
        if callable(get_calendar):
            _collect_datetime_candidates(get_calendar(), candidates)
    except Exception:
        pass

    if not candidates:
        return None

    unique_dates = sorted({ts.date() for ts in candidates})
    if not unique_dates:
        return None

    today = datetime.now(timezone.utc).date()
    future = [d for d in unique_dates if d >= (today - timedelta(days=1))]
    chosen = future[0] if future else unique_dates[-1]
    return chosen.isoformat()


def _get_prediction_fields_from_yfinance(symbol):
    empty = {
        "currency": None,
        "eps_forecast": None,
        "next_year_eps_forecast": None,
        "next_quarter_eps_forecast": None,
        "next_earnings_date": None,
    }
    if yf is None:
        return empty

    try:
        ticker = yf.Ticker(symbol)
    except Exception:
        return empty
    try:
        info = getattr(ticker, "info", None)
    except Exception:
        info = None
    info = info if isinstance(info, dict) else {}
    prediction_currency = _normalize_currency_code(
        _mapping_get_text(info, "financialCurrency", "currency")
    )

    estimate_df = None
    trend_df = None
    try:
        estimate_df = ticker.get_earnings_estimate()
    except Exception:
        estimate_df = getattr(ticker, "earnings_estimate", None)
    try:
        trend_df = ticker.get_eps_trend()
    except Exception:
        trend_df = getattr(ticker, "eps_trend", None)

    current_year = int(datetime.now(timezone.utc).year)
    current_tokens = {"0y", "+0y", "currentyear", "curryear", "curry", "current"}
    next_year_tokens = {"+1y", "1y", "nextyear", "nexty"}
    next_quarter_tokens = {"+1q", "1q", "nextquarter", "nextq"}
    current_quarter_tokens = {"0q", "+0q", "currentq", "currq"}

    def _year_from_token(token):
        m = re.search(r"(20\d{2})", str(token or ""))
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _is_current_year(token):
        token = _normalize_period_token(token)
        if token in current_tokens or token == str(current_year):
            return True
        return _year_from_token(token) == current_year

    def _is_next_year(token):
        token = _normalize_period_token(token)
        if token in next_year_tokens or token == str(current_year + 1):
            return True
        token_year = _year_from_token(token)
        if token_year == current_year + 1:
            return True
        return "y" in token and "q" not in token and token not in current_tokens

    def _is_next_quarter(token):
        token = _normalize_period_token(token)
        if token in next_quarter_tokens:
            return True
        return "q" in token and token not in current_quarter_tokens

    current_year_eps = _pick_eps_from_yfinance_frame(
        estimate_df,
        preferred_tokens=current_tokens,
        fallback_predicate=_is_current_year,
        candidate_cols=["avg", "current"],
    )
    if current_year_eps is None:
        current_year_eps = _pick_eps_from_yfinance_frame(
            trend_df,
            preferred_tokens=current_tokens,
            fallback_predicate=_is_current_year,
            candidate_cols=["current", "7daysAgo", "30daysAgo", "60daysAgo", "90daysAgo"],
        )

    next_year_eps = _pick_eps_from_yfinance_frame(
        estimate_df,
        preferred_tokens=next_year_tokens,
        fallback_predicate=_is_next_year,
        candidate_cols=["avg", "current"],
    )
    if next_year_eps is None:
        next_year_eps = _pick_eps_from_yfinance_frame(
            trend_df,
            preferred_tokens=next_year_tokens,
            fallback_predicate=_is_next_year,
            candidate_cols=["current", "7daysAgo", "30daysAgo", "60daysAgo", "90daysAgo"],
        )

    next_quarter_eps = _pick_eps_from_yfinance_frame(
        estimate_df,
        preferred_tokens=next_quarter_tokens,
        fallback_predicate=_is_next_quarter,
        candidate_cols=["avg", "current"],
    )
    if next_quarter_eps is None:
        next_quarter_eps = _pick_eps_from_yfinance_frame(
            trend_df,
            preferred_tokens=next_quarter_tokens,
            fallback_predicate=_is_next_quarter,
            candidate_cols=["current", "7daysAgo", "30daysAgo", "60daysAgo", "90daysAgo"],
        )

    return {
        "currency": prediction_currency,
        "eps_forecast": _round(current_year_eps),
        "next_year_eps_forecast": _round(next_year_eps),
        "next_quarter_eps_forecast": _round(next_quarter_eps),
        "next_earnings_date": _extract_next_earnings_date_from_yfinance_ticker(ticker),
    }


def _extract_next_earnings_date(qs):
    earnings_dates = _extract_raw(qs, ["calendarEvents", "earnings", "earningsDate"])
    timestamps = []
    text_dates = []

    if isinstance(earnings_dates, list):
        for item in earnings_dates:
            if isinstance(item, dict):
                raw = item.get("raw")
                if _is_number(raw):
                    timestamps.append(int(raw))
                elif item.get("fmt"):
                    text_dates.append(str(item.get("fmt")))
            elif _is_number(item):
                timestamps.append(int(item))
            elif isinstance(item, str):
                text_dates.append(item)
    elif _is_number(earnings_dates):
        timestamps.append(int(earnings_dates))
    elif isinstance(earnings_dates, str):
        text_dates.append(earnings_dates)

    if timestamps:
        now_ts = int(datetime.now(timezone.utc).timestamp()) - 86400
        future = [x for x in timestamps if x >= now_ts]
        selected = min(future) if future else min(timestamps)
        return _to_iso_date_from_epoch(selected)

    for text in text_dates:
        iso_date = _to_iso_date_from_text(text)
        if iso_date:
            return iso_date
    return None


def _get_forecast_from_yahoo(symbol):
    page = _parse_yahoo_pages(symbol)
    metrics = page.get("display_metrics", {})
    eps_trend = (
        page.get("analysis_eps_trend")
        if isinstance(page.get("analysis_eps_trend"), dict)
        else {"current_year_eps": None, "next_qtr_eps": None, "next_year_eps": None}
    )

    qs = {}
    if isinstance(page.get("quote_summary"), dict):
        qs.update(page.get("quote_summary"))
    qs.update(
        _yahoo_quote_summary(
            symbol,
            modules=["defaultKeyStatistics", "financialData", "summaryDetail", "earningsTrend", "calendarEvents"],
        )
    )

    forward_pe = _first_valid_number(
        metrics.get("Forward P/E"),
        _extract_raw(qs, ["defaultKeyStatistics", "forwardPE"]),
        _extract_raw(qs, ["financialData", "forwardPE"]),
    )
    peg = _first_valid_number(
        metrics.get("PEG Ratio (5yr expected)"),
        _extract_raw(qs, ["defaultKeyStatistics", "pegRatio"]),
    )
    ev_to_ebitda = _first_valid_number(
        metrics.get("Enterprise Value/EBITDA"),
        metrics.get("EV/EBITDA"),
        _extract_raw(qs, ["defaultKeyStatistics", "enterpriseToEbitda"]),
        _extract_raw(qs, ["financialData", "enterpriseToEbitda"]),
    )
    ps = _first_valid_number(
        metrics.get("Price/Sales (ttm)"),
        metrics.get("Price/Sales"),
        metrics.get("P/S"),
        _extract_raw(qs, ["summaryDetail", "priceToSalesTrailing12Months"]),
        _extract_raw(qs, ["defaultKeyStatistics", "priceToSalesTrailing12Months"]),
        _extract_raw(qs, ["financialData", "priceToSalesTrailing12Months"]),
    )
    pb = _first_valid_number(
        metrics.get("Price/Book (mrq)"),
        metrics.get("Price/Book"),
        metrics.get("P/B"),
        _extract_raw(qs, ["defaultKeyStatistics", "priceToBook"]),
        _extract_raw(qs, ["financialData", "priceToBook"]),
        _extract_raw(qs, ["summaryDetail", "priceToBook"]),
    )
    eps_forecast = _first_valid_number(
        eps_trend.get("current_year_eps"),
        _extract_raw(qs, ["defaultKeyStatistics", "forwardEps"]),
        _extract_raw(qs, ["financialData", "epsForward"]),
    )
    next_year_eps_forecast = _first_valid_number(
        eps_trend.get("next_year_eps"),
        metrics.get("Next Year EPS Estimate"),
        metrics.get("Next Year EPS Est"),
        metrics.get("Next Y EPS Est"),
        _extract_next_year_eps(qs),
    )
    next_quarter_eps_forecast = _first_valid_number(
        eps_trend.get("next_qtr_eps"),
        metrics.get("Next Qtr. EPS Est"),
        metrics.get("Current Qtr. EPS Est"),
        _extract_next_quarter_eps(qs),
    )
    next_earnings_date = _extract_next_earnings_date(qs)
    forecast_currency = _normalize_currency_code(
        _extract_raw(qs, ["summaryDetail", "currency"])
        or _extract_raw(qs, ["financialData", "financialCurrency"])
    )

    return {
        "currency": forecast_currency,
        "forward_pe": _round(forward_pe),
        "peg": _round(peg),
        "ev_to_ebitda": _round(ev_to_ebitda),
        "ps": _round(ps),
        "pb": _round(pb),
        "eps_forecast": _round(eps_forecast),
        "next_year_eps_forecast": _round(next_year_eps_forecast),
        "next_quarter_eps_forecast": _round(next_quarter_eps_forecast),
        "next_earnings_date": next_earnings_date,
    }


def _to_iso(ts):
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _fetch_news_finnhub(symbol, api_key, limit=NEWS_ITEMS_PER_STOCK):
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
    except Exception as exc:
        _record_fetch_issue("finnhub.company_news", exc=exc)
        return []


def _fetch_news_rss(symbol, limit=NEWS_ITEMS_PER_STOCK):
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
    except Exception as exc:
        _record_fetch_issue("yahoo.rss", exc=exc)
    return [i for i in items if i.get("title")]


def _get_recent_news(symbol, api_key, limit=NEWS_ITEMS_PER_STOCK):
    news = _fetch_news_finnhub(symbol, api_key, limit=limit)
    if news:
        return news[:limit]
    return _fetch_news_rss(symbol, limit=limit)


def _financial_cache_ttl_hours():
    raw = str(os.getenv("STOCKANALYSISKIT_FIN_CACHE_TTL_HOURS", "12")).strip()
    try:
        ttl = float(raw)
        return ttl if ttl > 0 else 12.0
    except Exception:
        return 12.0


def get_stock_bundle(
    symbol,
    finnhub_api_key,
    force_refresh_financial=False,
):
    token = _start_issue_collection()
    try:
        stock = _get_stock_bundle_inner(
            symbol=symbol,
            finnhub_api_key=finnhub_api_key,
            force_refresh_financial=force_refresh_financial,
        )
    finally:
        issues = _finish_issue_collection(token)

    if isinstance(stock, dict) and issues:
        stock["warnings"] = issues
    return stock


def _get_stock_bundle_inner(
    symbol,
    finnhub_api_key,
    force_refresh_financial=False,
):
    symbol = symbol.upper()
    finnhub_api_key = str(finnhub_api_key or "").strip()

    finnhub_bundle = {}
    realtime = {}
    if finnhub_api_key:
        try:
            finnhub_bundle = _finnhub_bundle(symbol, finnhub_api_key)
            realtime = _get_realtime_from_finnhub(finnhub_bundle)
        except Exception as exc:
            _record_fetch_issue("finnhub.bundle", exc=exc)
            finnhub_bundle = {}
            realtime = {}

    # 无 Finnhub Key 或 Finnhub 口径缺失时，使用 yfinance 兜底补齐。
    if not finnhub_api_key or realtime.get("price") is None:
        try:
            realtime = _merge_realtime_snapshot(realtime, _get_realtime_from_yfinance(symbol))
        except Exception as exc:
            _record_fetch_issue("yfinance.realtime", exc=exc)

    cached_payload = None
    if not force_refresh_financial:
        try:
            cached_payload = get_cached_financial_bundle(symbol, ttl_hours=_financial_cache_ttl_hours())
        except Exception as exc:
            _record_fetch_issue("cache.financial.read", exc=exc)
            cached_payload = None

    if isinstance(cached_payload, dict):
        financial = cached_payload.get("financial", {}) if isinstance(cached_payload.get("financial"), dict) else {}
        ai_financial_context = (
            cached_payload.get("ai_financial_context", {})
            if isinstance(cached_payload.get("ai_financial_context"), dict)
            else {}
        )
    else:
        financial = _get_financial_from_yfinance(symbol)
        ai_financial_context = _build_ai_financial_context_from_yfinance(
            symbol, annual_limit=3, quarterly_limit=4
        )
        try:
            set_cached_financial_bundle(symbol, financial, ai_financial_context)
        except Exception as exc:
            _record_fetch_issue("cache.financial.write", exc=exc)

    try:
        forecast = _get_forecast_from_yahoo(symbol)
    except Exception as exc:
        _record_fetch_issue("yahoo.forecast", exc=exc)
        forecast = {
            "currency": None,
            "forward_pe": None,
            "peg": None,
            "ev_to_ebitda": None,
            "ps": None,
            "pb": None,
            "eps_forecast": None,
            "next_year_eps_forecast": None,
            "next_quarter_eps_forecast": None,
            "next_earnings_date": None,
        }

    try:
        yfinance_prediction = _get_prediction_fields_from_yfinance(symbol)
    except Exception as exc:
        _record_fetch_issue("yfinance.prediction", exc=exc)
        yfinance_prediction = {
            "currency": None,
            "eps_forecast": None,
            "next_year_eps_forecast": None,
            "next_quarter_eps_forecast": None,
            "next_earnings_date": None,
        }

    forecast.update(
        {
            "currency": yfinance_prediction.get("currency") or forecast.get("currency"),
            "eps_forecast": _first_valid_number(
                yfinance_prediction.get("eps_forecast"),
                forecast.get("eps_forecast"),
            ),
            "next_year_eps_forecast": _first_valid_number(
                yfinance_prediction.get("next_year_eps_forecast"),
                forecast.get("next_year_eps_forecast"),
            ),
            "next_quarter_eps_forecast": _first_valid_number(
                yfinance_prediction.get("next_quarter_eps_forecast"),
                forecast.get("next_quarter_eps_forecast"),
            ),
            "next_earnings_date": (
                yfinance_prediction.get("next_earnings_date") or forecast.get("next_earnings_date")
            ),
        }
    )
    currency = _attach_currency_snapshot(
        symbol,
        realtime=realtime,
        financial=financial,
        forecast=forecast,
        finnhub_bundle=finnhub_bundle,
    )

    try:
        news = _get_recent_news(symbol, finnhub_api_key, limit=NEWS_ITEMS_PER_STOCK)
    except Exception as exc:
        _record_fetch_issue("news.aggregate", exc=exc)
        news = []
    try:
        expectation_guidance = _build_expectation_guidance_snapshot(
            symbol,
            news=news,
        )
    except Exception as exc:
        _record_fetch_issue("expectation_guidance", exc=exc)
        expectation_guidance = _empty_expectation_guidance_snapshot()

    stock = {
        "symbol": symbol,
        "currency": currency,
        "realtime": realtime,
        "financial": financial,
        "forecast": forecast,
        "ai_financial_context": ai_financial_context,
        "news": news,
        "expectation_guidance": expectation_guidance,
    }
    return stock


def _render_num(value):
    return "-" if value is None else str(value)


def _stock_section_currency(stock, section):
    stock = stock if isinstance(stock, dict) else {}
    currency = stock.get("currency", {}) if isinstance(stock.get("currency"), dict) else {}
    section_data = stock.get(section, {}) if isinstance(stock.get(section), dict) else {}

    if section == "forecast":
        return (
            _normalize_currency_code(section_data.get("currency"))
            or _normalize_currency_code(currency.get("forecast"))
            or _normalize_currency_code(currency.get("financial"))
            or _normalize_currency_code(currency.get("quote"))
        )
    if section == "financial":
        return (
            _normalize_currency_code(section_data.get("currency"))
            or _normalize_currency_code(currency.get("financial"))
            or _normalize_currency_code(currency.get("quote"))
        )
    if section == "realtime":
        return (
            _normalize_currency_code(section_data.get("currency"))
            or _normalize_currency_code(currency.get("quote"))
            or _normalize_currency_code(currency.get("financial"))
        )
    return None


def _format_financial_context_for_ai(context, currency_code=None):
    annual = context.get("annual", []) if isinstance(context, dict) else []
    quarterly = context.get("quarterly", []) if isinstance(context, dict) else []
    unit = f"B {currency_code}" if _normalize_currency_code(currency_code) else "B (Local Currency)"

    annual_lines = []
    for row in annual:
        annual_lines.append(
            "- {period}: Revenue({unit})={rev}, GrossMargin(%)={gm}, OpMargin(%)={om}, "
            "NetIncome({unit})={ni}, EPS(Diluted)={eps}, OCF({unit})={ocf}, FCF({unit})={fcf}".format(
                period=row.get("period_end") or "-",
                unit=unit,
                rev=_render_num(row.get("revenue_b")),
                gm=_render_num(row.get("gross_margin_pct")),
                om=_render_num(row.get("operating_margin_pct")),
                ni=_render_num(row.get("net_income_b")),
                eps=_render_num(row.get("eps_diluted")),
                ocf=_render_num(row.get("operating_cash_flow_b")),
                fcf=_render_num(row.get("free_cash_flow_b")),
            )
        )

    quarterly_lines = []
    for row in quarterly:
        quarterly_lines.append(
            "- {period} (FY{fy} Q{fq}): Revenue({unit})={rev}, GrossMargin(%)={gm}, "
            "OpMargin(%)={om}, NetIncome({unit})={ni}, EPS(Diluted)={eps}, OCF({unit})={ocf}, FCF({unit})={fcf}".format(
                period=row.get("period_end") or "-",
                fy=_render_num(row.get("fiscal_year")),
                fq=_render_num(row.get("fiscal_quarter")),
                unit=unit,
                rev=_render_num(row.get("revenue_b")),
                gm=_render_num(row.get("gross_margin_pct")),
                om=_render_num(row.get("operating_margin_pct")),
                ni=_render_num(row.get("net_income_b")),
                eps=_render_num(row.get("eps_diluted")),
                ocf=_render_num(row.get("operating_cash_flow_b")),
                fcf=_render_num(row.get("free_cash_flow_b")),
            )
        )

    return (
        "AI Financial Context - Annual (3Y):\n"
        + ("\n".join(annual_lines) if annual_lines else "- No annual data available")
        + "\nAI Financial Context - Quarterly (4Q):\n"
        + ("\n".join(quarterly_lines) if quarterly_lines else "- No quarterly data available")
    )


def _fmt_num(value, digits=2, suffix=""):
    if not _is_number(value):
        return "--"
    return f"{float(value):.{digits}f}{suffix}"


def _delta(a, b):
    if not _is_number(a) or not _is_number(b):
        return None
    return _round(float(a) - float(b))


def _latest_and_prev_quarter(quarterly):
    latest_q = quarterly[0] if len(quarterly) >= 1 else {}
    prev_q = quarterly[1] if len(quarterly) >= 2 else {}
    same_q_last_year = None
    if latest_q and _is_number(latest_q.get("fiscal_year")) and _is_number(latest_q.get("fiscal_quarter")):
        target_y = int(latest_q.get("fiscal_year")) - 1
        target_q = int(latest_q.get("fiscal_quarter"))
        for row in quarterly[1:]:
            if int(row.get("fiscal_year") or 0) == target_y and int(row.get("fiscal_quarter") or 0) == target_q:
                same_q_last_year = row
                break
    return latest_q, prev_q, same_q_last_year


def _annual_cagr_pct(annual):
    rows = [r for r in (annual or []) if _is_number(r.get("revenue_b"))]
    if len(rows) < 3:
        return None
    latest = float(rows[0].get("revenue_b"))
    oldest = float(rows[-1].get("revenue_b"))
    years = len(rows) - 1
    if latest <= 0 or oldest <= 0 or years <= 0:
        return None
    try:
        return _round(((latest / oldest) ** (1 / years) - 1) * 100)
    except Exception:
        return None


def _build_earnings_focus_commentary(stock):
    symbol = stock.get("symbol")
    context = stock.get("ai_financial_context", {}) if isinstance(stock, dict) else {}
    annual = context.get("annual", []) if isinstance(context, dict) else []
    quarterly = context.get("quarterly", []) if isinstance(context, dict) else []
    financial = stock.get("financial", {}) if isinstance(stock, dict) else {}
    forecast = stock.get("forecast", {}) if isinstance(stock, dict) else {}
    expectation_guidance = stock.get("expectation_guidance", {}) if isinstance(stock, dict) else {}
    beat_miss = expectation_guidance.get("beat_miss", {}) if isinstance(expectation_guidance, dict) else {}

    if not annual and not quarterly:
        return f"### {symbol}\n- 财报数据不足，暂无法形成有效点评。"

    latest_q, prev_q, same_q_last_year = _latest_and_prev_quarter(quarterly)
    latest_a = annual[0] if annual else {}
    prev_a = annual[1] if len(annual) >= 2 else {}
    oldest_a = annual[-1] if len(annual) >= 2 else {}

    latest_label = financial.get("latest_period") or latest_q.get("period_end") or latest_a.get("period_end") or "-"
    period_type = "季度" if str(financial.get("latest_period_type") or "").lower() == "quarterly" else "年度"

    annual_rev_cagr = _annual_cagr_pct(annual)
    annual_net_margin_latest = latest_a.get("net_margin_pct")
    annual_net_margin_prev = prev_a.get("net_margin_pct")
    annual_gm_latest = latest_a.get("gross_margin_pct")
    annual_gm_oldest = oldest_a.get("gross_margin_pct")
    annual_roe_latest = _to_bounded_pct(latest_a.get("net_income_b"), latest_a.get("shareholders_equity_b"))
    annual_roe_prev = _to_bounded_pct(prev_a.get("net_income_b"), prev_a.get("shareholders_equity_b"))
    annual_margin_trend = _delta(annual_net_margin_latest, annual_net_margin_prev)
    annual_gm_3y_change = _delta(annual_gm_latest, annual_gm_oldest)

    annual_score = 0
    if _is_number(annual_rev_cagr):
        annual_score += 2 if annual_rev_cagr >= 15 else (1 if annual_rev_cagr >= 8 else (-2 if annual_rev_cagr < 0 else 0))
    if _is_number(annual_roe_latest):
        annual_score += 2 if annual_roe_latest >= 18 else (1 if annual_roe_latest >= 12 else (-1 if annual_roe_latest < 8 else 0))
    if _is_number(annual_margin_trend):
        annual_score += 1 if annual_margin_trend >= 1.0 else (-1 if annual_margin_trend <= -1.0 else 0)
    if _is_number(annual_gm_3y_change):
        annual_score += 1 if annual_gm_3y_change >= 2.0 else (-1 if annual_gm_3y_change <= -2.0 else 0)

    if annual_score >= 5:
        annual_verdict = "商业模式竞争力强，规模扩张与盈利效率同步提升。"
    elif annual_score >= 2:
        annual_verdict = "商业模式竞争力中上，盈利能力处于改善通道。"
    elif annual_score >= 0:
        annual_verdict = "商业模式竞争力中性，增长与盈利改善仍需继续验证。"
    else:
        annual_verdict = "商业模式竞争力承压，长期盈利质量尚不稳固。"

    rev_q_yoy = _pct_change(latest_q.get("revenue_b"), same_q_last_year.get("revenue_b")) if latest_q and same_q_last_year else None
    rev_q_qoq = _pct_change(latest_q.get("revenue_b"), prev_q.get("revenue_b")) if latest_q and prev_q else None
    net_q_yoy = _pct_change(latest_q.get("net_income_b"), same_q_last_year.get("net_income_b")) if latest_q and same_q_last_year else None
    net_q_qoq = _pct_change(latest_q.get("net_income_b"), prev_q.get("net_income_b")) if latest_q and prev_q else None
    gm_latest = latest_q.get("gross_margin_pct") if latest_q else None
    gm_qoq = _delta(latest_q.get("gross_margin_pct"), prev_q.get("gross_margin_pct")) if latest_q and prev_q else None
    opm_latest = latest_q.get("operating_margin_pct") if latest_q else financial.get("operating_margin_pct")
    opm_qoq = _delta(latest_q.get("operating_margin_pct"), prev_q.get("operating_margin_pct")) if latest_q and prev_q else None
    ocf_latest = latest_q.get("operating_cash_flow_b") if latest_q else None
    fcf_latest = latest_q.get("free_cash_flow_b") if latest_q else None
    fcf_conversion = (
        _to_bounded_pct(fcf_latest, latest_q.get("net_income_b"))
        if latest_q and _is_number(latest_q.get("net_income_b")) and latest_q.get("net_income_b") != 0
        else None
    )

    quarter_score = 0
    if _is_number(rev_q_yoy):
        quarter_score += 2 if rev_q_yoy >= 20 else (1 if rev_q_yoy >= 8 else (-2 if rev_q_yoy < 0 else 0))
    if _is_number(net_q_yoy):
        quarter_score += 2 if net_q_yoy >= 15 else (1 if net_q_yoy >= 5 else (-2 if net_q_yoy < 0 else 0))
    if _is_number(opm_qoq):
        quarter_score += 1 if opm_qoq >= 1.0 else (-1 if opm_qoq <= -1.0 else 0)
    if _is_number(gm_qoq):
        quarter_score += 1 if gm_qoq >= 1.0 else (-1 if gm_qoq <= -1.0 else 0)
    if _is_number(fcf_conversion):
        quarter_score += 1 if fcf_conversion >= 80 else (-1 if fcf_conversion < 40 else 0)

    if quarter_score >= 5:
        quarter_verdict = "近4季度经营态势强劲，增长与利润率形成共振。"
    elif quarter_score >= 2:
        quarter_verdict = "近4季度经营态势改善，利润率与现金流质量同步修复。"
    elif quarter_score >= 0:
        quarter_verdict = "近4季度经营态势中性，关键指标分化，需继续跟踪。"
    else:
        quarter_verdict = "近4季度经营态势承压，利润与现金流稳定性偏弱。"

    annual_evidence = []
    if _is_number(annual_rev_cagr):
        if annual_rev_cagr >= 20:
            growth_view = "规模扩张速度快，需求与份额提升具备持续性"
        elif annual_rev_cagr >= 8:
            growth_view = "规模保持稳健扩张，增长质量整体可接受"
        elif annual_rev_cagr >= 0:
            growth_view = "规模扩张偏温和，增长斜率仍需进一步抬升"
        else:
            growth_view = "规模出现收缩，商业扩张动能不足"
        annual_evidence.append(f"收入三年复合增速约 {_fmt_num(annual_rev_cagr, suffix='%')}，{growth_view}")

    margin_bits = []
    if _is_number(annual_margin_trend):
        if annual_margin_trend >= 1.0:
            margin_bits.append("净利率中枢上移")
        elif annual_margin_trend <= -1.0:
            margin_bits.append("净利率中枢下移")
        else:
            margin_bits.append("净利率大体稳定")
    if _is_number(annual_gm_3y_change):
        if annual_gm_3y_change >= 2.0:
            margin_bits.append("毛利率中枢抬升")
        elif annual_gm_3y_change <= -2.0:
            margin_bits.append("毛利率中枢下移")
    if margin_bits:
        annual_evidence.append("盈利结构上，" + "、".join(margin_bits))

    if _is_number(annual_roe_latest):
        if annual_roe_latest >= 18:
            roe_view = "资本回报效率处于高位"
        elif annual_roe_latest >= 12:
            roe_view = "资本回报效率处于中上水平"
        elif annual_roe_latest >= 8:
            roe_view = "资本回报效率中性"
        else:
            roe_view = "资本回报效率偏弱"

        roe_trend = ""
        if _is_number(annual_roe_prev):
            if annual_roe_latest - annual_roe_prev >= 2.0:
                roe_trend = "，且较上年改善"
            elif annual_roe_latest - annual_roe_prev <= -2.0:
                roe_trend = "，且较上年回落"
            else:
                roe_trend = "，与上年基本持平"
        annual_evidence.append(f"ROE 约 {_fmt_num(annual_roe_latest, suffix='%')}，{roe_view}{roe_trend}")

    annual_line = ("；".join(annual_evidence[:3]) if annual_evidence else "三年核心指标可用性有限") + f"。{annual_verdict}"

    def _growth_summary(metric_name, yoy_val, qoq_val, strong=20, moderate=8):
        if _is_number(yoy_val):
            delta = float(yoy_val)
            basis = "较上年同期"
        elif _is_number(qoq_val):
            delta = float(qoq_val)
            basis = "较上一季度"
        else:
            return None, None

        abs_delta = abs(delta)
        if delta >= 0:
            if abs_delta >= strong:
                strength = "动能强"
            elif abs_delta >= moderate:
                strength = "保持增长"
            else:
                strength = "增速温和"
            return f"{metric_name}{basis}增长{_fmt_num(abs_delta, suffix='%')}，{strength}", delta

        if abs_delta >= strong:
            strength = "回落明显"
        elif abs_delta >= moderate:
            strength = "有所承压"
        else:
            strength = "基本持平"
        return f"{metric_name}{basis}下滑{_fmt_num(abs_delta, suffix='%')}，{strength}", delta

    rev_summary, rev_delta = _growth_summary("收入", rev_q_yoy, rev_q_qoq)
    net_summary, net_delta = _growth_summary("净利润", net_q_yoy, net_q_qoq)

    growth_joint_view = None
    if _is_number(rev_delta) and _is_number(net_delta):
        if rev_delta >= 0 and net_delta >= 0:
            if net_delta - rev_delta >= 8:
                growth_joint_view = "收入与利润同向扩张，且利润弹性高于收入，经营杠杆释放较充分"
            else:
                growth_joint_view = "收入与利润同向扩张，增长质量较为扎实"
        elif rev_delta >= 0 > net_delta:
            growth_joint_view = "收入维持增长但利润未跟上，短期成本或费用压力抬升"
        elif rev_delta < 0 <= net_delta:
            growth_joint_view = "收入承压但利润改善，费用与产品结构优化起到缓冲作用"
        else:
            growth_joint_view = "收入与利润同步走弱，短期经营景气偏弱"
    elif rev_summary or net_summary:
        growth_joint_view = "当前增长信号有限，以已有披露口径做阶段性判断"

    margin_phrase = None
    if _is_number(opm_latest):
        if _is_number(opm_qoq):
            if opm_qoq >= 1.0:
                margin_phrase = f"经营利润率约 {_fmt_num(opm_latest, suffix='%')}，边际改善，盈利效率继续修复"
            elif opm_qoq <= -1.0:
                margin_phrase = f"经营利润率约 {_fmt_num(opm_latest, suffix='%')}，边际回落，需跟踪费用率与价格压力"
            else:
                margin_phrase = f"经营利润率约 {_fmt_num(opm_latest, suffix='%')}，边际基本稳定"
        else:
            margin_phrase = f"经营利润率约 {_fmt_num(opm_latest, suffix='%')}，处于当前周期可接受区间"
    elif _is_number(gm_latest):
        margin_phrase = f"毛利率约 {_fmt_num(gm_latest, suffix='%')}，反映产品结构与定价能力"

    cash_phrase = None
    if _is_number(fcf_conversion):
        if fcf_conversion >= 90:
            cash_phrase = "利润向现金流转化效率高，财报兑现质量较好"
        elif fcf_conversion >= 60:
            cash_phrase = "利润向现金流转化处于中性，需继续观察回款与资本开支节奏"
        else:
            cash_phrase = "利润向现金流转化偏弱，需关注应收、库存与开支强度"
    elif _is_number(ocf_latest) and _is_number(fcf_latest):
        if ocf_latest > 0 and fcf_latest > 0:
            cash_phrase = "经营现金流与自由现金流均为正，现金流安全垫尚可"
        elif ocf_latest > 0 >= fcf_latest:
            cash_phrase = "经营现金流为正但自由现金流偏弱，资本开支或营运资本占用较高"
        else:
            cash_phrase = "现金流质量偏弱，后续需重点验证回款能力"

    anchor_phrase = None
    if _is_number(rev_q_yoy):
        if rev_q_yoy >= 0:
            anchor_phrase = f"关键锚点是收入较上年同期增长{_fmt_num(rev_q_yoy, suffix='%')}"
        else:
            anchor_phrase = f"关键锚点是收入较上年同期下滑{_fmt_num(abs(rev_q_yoy), suffix='%')}"
    elif _is_number(rev_q_qoq):
        if rev_q_qoq >= 0:
            anchor_phrase = f"关键锚点是收入较上一季度增长{_fmt_num(rev_q_qoq, suffix='%')}"
        else:
            anchor_phrase = f"关键锚点是收入较上一季度下滑{_fmt_num(abs(rev_q_qoq), suffix='%')}"
    elif _is_number(net_q_yoy):
        if net_q_yoy >= 0:
            anchor_phrase = f"关键锚点是净利润较上年同期增长{_fmt_num(net_q_yoy, suffix='%')}"
        else:
            anchor_phrase = f"关键锚点是净利润较上年同期下滑{_fmt_num(abs(net_q_yoy), suffix='%')}"
    elif _is_number(net_q_qoq):
        if net_q_qoq >= 0:
            anchor_phrase = f"关键锚点是净利润较上一季度增长{_fmt_num(net_q_qoq, suffix='%')}"
        else:
            anchor_phrase = f"关键锚点是净利润较上一季度下滑{_fmt_num(abs(net_q_qoq), suffix='%')}"

    quarter_evidence = []
    if growth_joint_view:
        quarter_evidence.append(growth_joint_view)
        if anchor_phrase:
            quarter_evidence.append(anchor_phrase)
    else:
        if rev_summary:
            quarter_evidence.append(rev_summary)
        if net_summary:
            quarter_evidence.append(net_summary)
    if margin_phrase:
        quarter_evidence.append(margin_phrase)
    if cash_phrase:
        quarter_evidence.append(cash_phrase)

    quarter_line = ("；".join(quarter_evidence[:4]) if quarter_evidence else "近四季度关键指标可用性有限") + f"。{quarter_verdict}"

    latest_beat_quarter = beat_miss.get("latest_quarter") or latest_label
    latest_eps_actual = beat_miss.get("latest_eps_actual")
    latest_eps_estimate = beat_miss.get("latest_eps_estimate")
    latest_surprise_pct = beat_miss.get("latest_surprise_pct")
    latest_result = str(beat_miss.get("latest_result") or "").strip().lower()
    if (
        latest_result not in {"beat", "miss", "inline"}
        and _is_number(latest_eps_actual)
        and _is_number(latest_eps_estimate)
        and float(latest_eps_estimate) != 0
    ):
        inferred_surprise = _pct_change(latest_eps_actual, latest_eps_estimate)
        if _is_number(inferred_surprise):
            latest_surprise_pct = latest_surprise_pct if _is_number(latest_surprise_pct) else inferred_surprise
            latest_result = _classify_surprise(latest_surprise_pct)

    if latest_result == "beat":
        latest_eval = "财报超预期"
    elif latest_result == "miss":
        latest_eval = "财报低于预期"
    elif latest_result == "inline":
        latest_eval = "财报符合预期"
    else:
        latest_eval = "财报超预期判断信息不足"

    latest_bits = [f"最新财报（{latest_beat_quarter}）{latest_eval}"]
    if _is_number(latest_eps_actual) and _is_number(latest_eps_estimate):
        latest_bits.append(f"EPS实际 {_fmt_num(latest_eps_actual)} vs 预期 {_fmt_num(latest_eps_estimate)}")
    if _is_number(latest_surprise_pct):
        latest_bits.append(f"surprise {_fmt_num(latest_surprise_pct, suffix='%')}")

    next_quarter_eps = forecast.get("next_quarter_eps_forecast")
    next_earnings_date = forecast.get("next_earnings_date")
    if _is_number(next_quarter_eps):
        next_quarter_phrase = f"下季度EPS预测约 {_fmt_num(next_quarter_eps)}"
    else:
        next_quarter_phrase = "下季度EPS预测信息不足"
    if next_earnings_date:
        next_quarter_phrase += f"，下次财报日 {next_earnings_date}"

    beat_count_4q = beat_miss.get("beat_count_4q")
    miss_count_4q = beat_miss.get("miss_count_4q")
    expectation_score = 0
    if latest_result == "beat":
        expectation_score += 1
    elif latest_result == "miss":
        expectation_score -= 1

    if _is_number(beat_count_4q) and _is_number(miss_count_4q):
        beat_count_int = int(beat_count_4q)
        miss_count_int = int(miss_count_4q)
        if beat_count_int >= 3 and miss_count_int <= 1:
            revision_phrase = "近4季预期兑现偏强，预期修正方向整体偏正面"
            expectation_score += 1
        elif miss_count_int >= 2 and beat_count_int <= 1:
            revision_phrase = "近4季 miss 偏多，预期修正与兑现风险仍需警惕"
            expectation_score -= 1
        else:
            revision_phrase = "近4季超预期与未达预期交错，预期修正信号分化"
    else:
        revision_phrase = "预期修正信息不足（缺少分析师上修/下修明细）"

    expectation_line = "；".join(["；".join(latest_bits), next_quarter_phrase, revision_phrase])

    if annual_score >= 2 and quarter_score >= 2:
        verdict = "长期竞争力与短期经营趋势一致向上，本次财报质量高于行业中位。"
    elif annual_score >= 2 and quarter_score < 2:
        verdict = "长期竞争力仍在，但短期经营动能边际走弱，需关注后续季度验证。"
    elif annual_score < 2 and quarter_score >= 2:
        verdict = "短期经营改善明显，但长期竞争力仍待巩固，财报可定性为阶段性修复。"
    else:
        verdict = "长期与短期指标均缺乏共振，财报结论偏谨慎。"

    if expectation_score >= 1:
        verdict += " 预期兑现与下季度预测信号偏正面。"
    elif expectation_score <= -1:
        verdict += " 预期兑现与下季度预测信号偏谨慎。"
    else:
        verdict += " 预期兑现证据有限，需继续跟踪下一次财报与预期修正。"

    return (
        f"### {symbol}\n"
        f"- 最新财报期: {latest_label}（{period_type}）\n"
        f"- 近3年财务（商业模式竞争力 / 3Y）: {annual_line}\n"
        f"- 近4季度财务（中短期经营态势 / 4Q）: {quarter_line}\n"
        f"- 最新财报与下季度财报预测（预期修正/超预期判断）: {expectation_line}\n"
        f"- 总体结论: {verdict}"
    )


def _select_requested_stocks(symbols, stocks):
    if not isinstance(stocks, list) or not stocks:
        return []

    requested = [str(s).upper() for s in (symbols or []) if str(s).strip()]
    order = {s: i for i, s in enumerate(requested)}
    selected = [
        stock
        for stock in stocks
        if isinstance(stock, dict)
        and stock.get("symbol")
        and (not requested or str(stock.get("symbol")).upper() in order)
    ]
    if requested:
        selected.sort(key=lambda item: order.get(str(item.get("symbol")).upper(), 999))
    return selected


def _ensure_reference_links(text, stocks=None):
    return text


def _generate_financial_analysis_local(symbols, stocks):
    if not isinstance(stocks, list) or not stocks:
        return "缺少可分析的股票数据，无法生成财务分析。"

    selected = _select_requested_stocks(symbols, stocks)
    if not selected:
        return "缺少可分析的股票数据，无法生成财务分析。"

    sections = []
    for stock in selected:
        symbol = str(stock.get("symbol") or "").upper()
        try:
            sections.append(_build_earnings_focus_commentary(stock))
        except Exception:
            sections.append(f"### {symbol}\n- 财报数据不足，暂无法形成有效点评。")

    return "\n\n".join(section for section in sections if section).strip() or "暂无可用财务分析。"


def _financial_ai_annual_lines(annual_rows):
    lines = []
    for row in annual_rows[:3]:
        roe = _to_bounded_pct(row.get("net_income_b"), row.get("shareholders_equity_b"))
        lines.append(
            "- {period}: Revenue(B)={rev}, NetMargin(%)={nm}, FCF(B)={fcf}, ROE(%)={roe}".format(
                period=row.get("period_end") or "-",
                rev=_render_num(row.get("revenue_b")),
                nm=_render_num(row.get("net_margin_pct")),
                fcf=_render_num(row.get("free_cash_flow_b")),
                roe=_render_num(roe),
            )
        )
    return lines


def _financial_ai_quarterly_lines(quarterly_rows):
    lines = []
    for row in quarterly_rows[:4]:
        lines.append(
            "- {period} (FY{fy} Q{fq}): Revenue(B)={rev}, GrossMargin(%)={gm}, "
            "OpMargin(%)={om}, NetIncome(B)={ni}, FCF(B)={fcf}".format(
                period=row.get("period_end") or "-",
                fy=_render_num(row.get("fiscal_year")),
                fq=_render_num(row.get("fiscal_quarter")),
                rev=_render_num(row.get("revenue_b")),
                gm=_render_num(row.get("gross_margin_pct")),
                om=_render_num(row.get("operating_margin_pct")),
                ni=_render_num(row.get("net_income_b")),
                fcf=_render_num(row.get("free_cash_flow_b")),
            )
        )
    return lines


def _build_financial_analysis_stock_context(stock):
    symbol = stock.get("symbol")
    financial = stock.get("financial", {}) if isinstance(stock, dict) else {}
    forecast = stock.get("forecast", {}) if isinstance(stock, dict) else {}
    expectation_guidance = stock.get("expectation_guidance", {}) if isinstance(stock, dict) else {}
    beat_miss = expectation_guidance.get("beat_miss", {}) if isinstance(expectation_guidance, dict) else {}
    context = stock.get("ai_financial_context", {}) if isinstance(stock, dict) else {}
    annual_rows = context.get("annual", []) if isinstance(context, dict) else []
    quarterly_rows = context.get("quarterly", []) if isinstance(context, dict) else []
    news = stock.get("news", []) if isinstance(stock, dict) else []

    news_lines = []
    for n in news[:NEWS_ITEMS_PER_STOCK]:
        title = n.get("title")
        publisher = n.get("publisher") or ""
        published_at = n.get("published_at") or ""
        if title:
            news_lines.append(f"- {title} | {publisher} | {published_at}")

    return (
        f"股票: {symbol}\n"
        f"最新财务摘要: period={financial.get('latest_period')}, type={financial.get('latest_period_type')}, "
        f"revenue_b={financial.get('revenue_b')}, revenue_yoy_pct={financial.get('revenue_yoy_pct')}, "
        f"net_income_b={financial.get('net_income_b')}, net_income_yoy_pct={financial.get('net_income_yoy_pct')}, "
        f"gross_margin_pct={financial.get('gross_margin_pct')}, operating_margin_pct={financial.get('operating_margin_pct')}, "
        f"net_margin_pct={financial.get('net_margin_pct')}, eps={financial.get('eps')}\n"
        f"最新财报预期兑现: latest_quarter={beat_miss.get('latest_quarter')}, latest_result={beat_miss.get('latest_result')}, "
        f"latest_surprise_pct={beat_miss.get('latest_surprise_pct')}, latest_eps_actual={beat_miss.get('latest_eps_actual')}, "
        f"latest_eps_estimate={beat_miss.get('latest_eps_estimate')}, beat_count_4q={beat_miss.get('beat_count_4q')}, "
        f"miss_count_4q={beat_miss.get('miss_count_4q')}\n"
        f"预期参考: next_quarter_eps_forecast={forecast.get('next_quarter_eps_forecast')}, "
        f"eps_forecast={forecast.get('eps_forecast')}, next_earnings_date={forecast.get('next_earnings_date')}\n"
        "近3年年度财务:\n"
        + ("\n".join(_financial_ai_annual_lines(annual_rows)) if annual_rows else "- No annual data")
        + "\n近4季度财务:\n"
        + ("\n".join(_financial_ai_quarterly_lines(quarterly_rows)) if quarterly_rows else "- No quarterly data")
        + "\n近期新闻:\n"
        + ("\n".join(news_lines) if news_lines else "- No recent news")
    )


def _build_financial_analysis_prompt(symbols, stocks, external_search_context=None, language="zh"):
    selected = _select_requested_stocks(symbols, stocks)
    if not selected:
        return None

    today_utc = datetime.now(timezone.utc).date().isoformat()
    blocks = [_build_financial_analysis_stock_context(stock) for stock in selected]
    symbols_str = ", ".join(str(s.get("symbol")) for s in selected if s.get("symbol"))
    has_external_search = bool(str(external_search_context or "").strip())
    search_requirement = (
        "- 优先使用下方“外部搜索结果（由 Exa/Tavily 提供）”进行判断；不要再调用模型搜索工具。"
        if has_external_search
        else "- 可以调用模型搜索能力作为兜底，优先查找近60天财报相关新闻与研报评价并融合进判断。"
    )
    search_block = (
        f"\n外部搜索结果（由 Exa/Tavily 提供）：\n{str(external_search_context).strip()}\n"
        if has_external_search
        else ""
    )
    is_en = _is_english(language)

    if is_en:
        search_requirement_en = (
            "- Prioritize the external search results below (from Exa/Tavily); do not call model search tools again."
            if has_external_search
            else "- You may use model search as fallback, prioritizing earnings news and analyst notes from the last 60 days."
        )
        search_block_en = (
            f"\nExternal search results (from Exa/Tavily):\n{str(external_search_context).strip()}\n"
            if has_external_search
            else ""
        )
        min_sources = 3 if len(selected) <= 1 else 5
        return f"""
You are a global equity financial analyst. Produce a "Financial Analysis" report for: {symbols_str}. Date (UTC): {today_utc}.

Required framework (from long-term to near-term):
1) Analyze the last 3 fiscal years: revenue growth, margins, free cash flow, and ROE. Judge business model strength and long-term operating trend.
2) Analyze the last 4 quarters: revenue/profit growth and margin profile. Judge whether short- to mid-term operations are strengthening or weakening.
3) Review the latest earnings and next-quarter forecast, and include a dedicated section for "Estimate Revisions & Earnings Assessment (latest report + next quarter)".
4) End with an overall conclusion.

Hard requirements:
- Lead with conclusions and avoid mechanical data dumping; cite at most 2-3 key numbers per section.
{search_requirement_en}
- If evidence for surprise/revision is insufficient, explicitly write "Information insufficient" and specify what is missing (surprise, analyst revisions, or next-quarter consensus).
- Keep this section strictly financial; do not provide buy/sell decisions or 3-6 month investment advice.
- Output must be English Markdown (no JSON/HTML).
- Provide references with title/institution, date, and link. Minimum {min_sources} sources.

Output structure (must include all lines for each stock):
### {{Ticker}}
- Latest reporting period:
- Last 3 years (competitiveness & long-term trend):
- Last 4 quarters (short/mid-term operating trend):
- Latest report + next-quarter forecast (revision/surprise assessment):
- Overall conclusion:

## References

{search_block_en}
Stock context:
{chr(10).join(blocks)}
""".strip()

    return f"""
你是全球股票财务分析专家。请对以下股票做“财务分析”模块输出：{symbols_str}。当前日期（UTC）: {today_utc}。
你必须按以下分析框架执行（由远及近）：
1) 先分析近3年财务数据：关注营收增速、利润率、自由现金流、ROE，判断商业模式竞争力与长期经营趋势。
2) 再分析近4季度财务数据：关注营收/利润增速与毛利率水平，判断中短期经营态势是否强化或走弱。
3) 点评最新财报与下季度财报预测，并单列“预期修正与财报评价（最新财报+下季度预测）”：判断本次财报是超预期/符合预期/低于预期；重点结合 EPS surprise、分析师预期修正、下一季 EPS 预测与卖方观点。
4) 最后给“总体结论”。

硬性要求：
- 结论先行，避免机械罗列数据；每个部分最多引用2-3个关键数字。
{search_requirement}
- 如果“超预期/预期修正”证据不足，必须明确写“信息不足”，并说明缺失项（至少指出缺少 surprise、分析师修正或下季度一致预期中的哪一项）。
- 只做财务分析，不要给3-6个月投资建议，不要输出买入/卖出结论（第5部分会处理）。
- 输出必须是中文 Markdown，不要 JSON/HTML。
- 给出参考来源，至少3条（单股）/5条（多股），含标题或机构名、日期、链接。

输出结构（每只股票都必须完整包含以下5行）：
### {{股票代码}}
- 最新财报期:
- 近3年财务（竞争力与长期趋势）:
- 近4季度财务（中短期经营态势）:
- 最新财报与下季度财报预测（预期修正/超预期判断）:
- 总体结论:

{search_block}
股票上下文：
{chr(10).join(blocks)}
""".strip()


def _generate_financial_analysis_with_ai(
    symbols,
    stocks,
    provider,
    api_key,
    model,
    base_url=None,
    exa_api_key=None,
    tavily_api_key=None,
    language="zh",
):
    external_search_context = _build_external_search_context(
        symbols=symbols,
        mode="financial",
        exa_api_key=exa_api_key,
        tavily_api_key=tavily_api_key,
        lookback_days=60,
    )
    lang = _normalize_ui_language(language)
    prompt = _build_financial_analysis_prompt(
        symbols,
        stocks,
        external_search_context=external_search_context,
        language=lang,
    )
    if not prompt:
        return "", "Missing stock context for analysis." if lang == "en" else "缺少可分析的股票上下文。"
    if not api_key or not model:
        return "", "AI API key or model is not configured." if lang == "en" else "未配置 AI API Key 或模型名。"

    return _run_ai_with_auto_continue(
        provider=provider,
        prompt=prompt,
        api_key=api_key,
        model=model,
        base_url=base_url,
        enable_model_search=not bool(str(external_search_context or "").strip()),
        continue_prompt=(
            "Continue only the unfinished part. Do not repeat previous text. Finish with overall conclusion and references."
            if lang == "en"
            else "继续未完成部分，不要重复已输出内容，完成到最后的“总体结论”和“参考来源”。"
        ),
        language=lang,
    )


def generate_financial_analysis(
    symbols,
    stocks,
    provider=None,
    api_key=None,
    model=None,
    base_url=None,
    exa_api_key=None,
    tavily_api_key=None,
    language="zh",
):
    local_text = _generate_financial_analysis_local(symbols, stocks)
    lang = _normalize_ui_language(language)
    if api_key and model:
        try:
            ai_result = _generate_financial_analysis_with_ai(
                symbols=symbols,
                stocks=stocks,
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
                exa_api_key=exa_api_key,
                tavily_api_key=tavily_api_key,
                language=lang,
            )
        except TypeError as exc:
            # 测试替身可能仍是旧签名，不接受新增参数。
            if (
                "exa_api_key" not in str(exc)
                and "tavily_api_key" not in str(exc)
                and "language" not in str(exc)
            ):
                raise
            try:
                ai_result = _generate_financial_analysis_with_ai(
                    symbols=symbols,
                    stocks=stocks,
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    language=lang,
                )
            except TypeError as nested_exc:
                if "language" not in str(nested_exc):
                    raise
                ai_result = _generate_financial_analysis_with_ai(
                    symbols=symbols,
                    stocks=stocks,
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                )
        if isinstance(ai_result, tuple):
            ai_text = str(ai_result[0] or "")
            ai_error = str(ai_result[1] or "")
        else:
            ai_text = str(ai_result or "")
            ai_error = ""
        if str(ai_text or "").strip():
            return _ensure_reference_links(ai_text, stocks=stocks)
        if ai_error:
            LOGGER.warning("AI financial analysis failed, fallback to local: %s", ai_error)
    return local_text


def _compact_stock_context(stock):
    symbol = stock.get("symbol")
    rt = stock.get("realtime", {})
    fc = stock.get("forecast", {})
    news = stock.get("news", [])

    headline_lines = []
    for n in news[:NEWS_ITEMS_PER_STOCK]:
        title = n.get("title")
        publisher = n.get("publisher") or ""
        published_at = n.get("published_at") or ""
        if title:
            headline_lines.append(f"- {title} | {publisher} | {published_at}")

    return (
        f"股票: {symbol}\n"
        f"近况参考: 日涨跌幅={rt.get('change_pct')}%, 5日={rt.get('change_5d_pct')}%, 20日={rt.get('change_20d_pct')}%, 250日={rt.get('change_250d_pct')}%\n"
        f"估值参考: PE(TTM)={rt.get('pe_ttm')}, Forward PE={fc.get('forward_pe')}, PEG={fc.get('peg')}, 下季度EPS={fc.get('next_quarter_eps_forecast')}, 下次财报日={fc.get('next_earnings_date')}\n"
        + _format_financial_context_for_ai(
            stock.get("ai_financial_context"),
            currency_code=_stock_section_currency(stock, "financial"),
        )
        + "\n"
        f"相关新闻:\n" + ("\n".join(headline_lines) if headline_lines else "- 无可用新闻")
    )


def _build_target_price_stock_context(stock):
    symbol = stock.get("symbol")
    rt = stock.get("realtime", {}) if isinstance(stock, dict) else {}
    fc = stock.get("forecast", {}) if isinstance(stock, dict) else {}
    news = stock.get("news", []) if isinstance(stock, dict) else []
    eps_anchor_value = None
    eps_anchor_source = "无可用EPS预测"
    eps_anchor_note = "未回退"
    if _is_number(fc.get("next_year_eps_forecast")):
        eps_anchor_value = _round(fc.get("next_year_eps_forecast"))
        eps_anchor_source = "next_year_eps_forecast"
    elif _is_number(fc.get("next_quarter_eps_forecast")):
        eps_anchor_value = _round(float(fc.get("next_quarter_eps_forecast")) * 4)
        eps_anchor_source = "next_quarter_eps_forecast × 4"
        eps_anchor_note = "已回退口径"

    headline_lines = []
    for n in news[:NEWS_ITEMS_PER_STOCK]:
        title = n.get("title")
        publisher = n.get("publisher") or ""
        published_at = n.get("published_at") or ""
        if title:
            headline_lines.append(f"- {title} | {publisher} | {published_at}")

    return (
        f"股票: {symbol}\n"
        f"价格与走势参考: 当前价={rt.get('price')}, 日涨跌幅={rt.get('change_pct')}%, 20日={rt.get('change_20d_pct')}%, 250日={rt.get('change_250d_pct')}%\n"
        f"估值锚点: PE(TTM)={rt.get('pe_ttm')}, Forward PE={fc.get('forward_pe')}, PEG={fc.get('peg')}, EV/EBITDA={fc.get('ev_to_ebitda')}, P/S={fc.get('ps')}, P/B={fc.get('pb')}\n"
        f"盈利预测锚点: 当前年EPS={fc.get('eps_forecast')}, 下一年EPS={fc.get('next_year_eps_forecast')}, 下季度EPS={fc.get('next_quarter_eps_forecast')}, 下次财报日={fc.get('next_earnings_date')}\n"
        f"目标价计算口径: 目标价 = Forward PE × EPS；EPS 仅使用 next_year_eps_forecast，若缺失则回退到 next_quarter_eps_forecast × 4；当前建议EPS锚点={eps_anchor_value}（来源={eps_anchor_source}，{eps_anchor_note}）\n"
        + _format_financial_context_for_ai(
            stock.get("ai_financial_context"),
            currency_code=_stock_section_currency(stock, "financial"),
        )
        + "\n"
        f"相关新闻:\n" + ("\n".join(headline_lines) if headline_lines else "- 无可用新闻")
    )


def _build_target_price_prompt(symbols, stocks, external_search_context=None, language="zh"):
    blocks = [_build_target_price_stock_context(stock) for stock in stocks if stock.get("symbol") in symbols]
    if not blocks:
        return None

    today_utc = datetime.now(timezone.utc).date().isoformat()
    has_external_search = bool(str(external_search_context or "").strip())
    search_requirement_text = (
        "优先使用下方“外部搜索结果（由 Exa/Tavily 提供）”；不要再调用模型搜索工具。"
        if has_external_search
        else "必须调用模型搜索能力，补充最新新闻、研报与估值观点；优先近45天信息。"
    )
    search_block = (
        f"\n外部搜索结果（由 Exa/Tavily 提供）：\n{str(external_search_context).strip()}\n"
        if has_external_search
        else ""
    )
    min_sources = 3 if len(symbols) <= 1 else 5
    is_en = _is_english(language)

    if is_en:
        search_requirement_text_en = (
            "Prioritize external search results below (from Exa/Tavily); do not call model search tools again."
            if has_external_search
            else "Use model search to supplement the latest news/research, prioritizing the last 45 days."
        )
        search_block_en = (
            f"\nExternal search results (from Exa/Tavily):\n{str(external_search_context).strip()}\n"
            if has_external_search
            else ""
        )
        return f"""
You are a global equity valuation analyst. Provide scenario-based target price analysis for: {', '.join(symbols)}. Date (UTC): {today_utc}.
Core task:
- Build bull/base/bear scenarios and provide valuation ranges and 3-6 month target price ranges for each stock.
- Each scenario must include key assumptions and be auditable.

Hard requirements:
1) {search_requirement_text_en}
2) Use fixed formula: Target Price = EPS (next year) × Target PE. PE must be next-year perspective, not just current spot forward PE.
3) Explicitly show the relationship: Target Price = Forward PE × EPS (Forward PE here means next-year target PE range).
4) EPS must use next_year_eps_forecast; if missing, fallback to next_quarter_eps_forecast × 4 and label as fallback. If still missing, write "Information insufficient".
5) Target PE must use three anchors with fixed weights: 40% / 35% / 25%.
6) Anchor A: prioritize 5-year average forward PE; 3-year average only for mean-reversion direction check.
7) Anchor B: PEG adjustment uses Bull/Base/Bear = 1.4/1.2/1.0 with next-year profit growth constraints.
8) Anchor C: auto-select 3-5 comparable peers.
9) Sentiment adjustment capped at ±5%; PE shift fixed at +15% / 0 / -15% for Bull / Base / Bear.
10) Each stock must include all three scenarios and each scenario must include EPS basis, target PE range, target price range, and 2-4 key assumptions.
11) Show final target PE ranges only; do not show intermediate A/B/C calculations.
12) Use ranges (prefer integer/rounded bands), not over-precise decimals.
13) If data is insufficient, explicitly say "Information insufficient" and list missing items.
14) Output must be English Markdown (no JSON/HTML).
15) Include at least {min_sources} references with title/institution, date, and link.

Recommended output structure (required lines for each stock):
### {{Ticker}}
- Bull scenario: EPS basis=...; target PE range=...; target price range=... (Target Price = Forward PE × EPS); key assumptions=...
- Base scenario: EPS basis=...; target PE range=...; target price range=... (Target Price = Forward PE × EPS); key assumptions=...
- Bear scenario: EPS basis=...; target PE range=...; target price range=... (Target Price = Forward PE × EPS); key assumptions=...
- Scenario conclusion:

## References

{search_block_en}
Stock context:
{chr(10).join(blocks)}
""".strip()

    return f"""
你是全球股票估值分析师。请对以下股票给出“目标价”情景分析：{', '.join(symbols)}。当前日期（UTC）: {today_utc}。
核心任务：
- 基于 bull / base / bear 三种情景，给出每只股票的估值区间与3-6个月目标价区间。
- 每个情景都需要给出关键假设，并确保逻辑可复核。

硬性要求：
1) {search_requirement_text}
2) 主公式固定为：目标价 = EPS(next year) × 目标PE。PE 口径使用 next year 视角下的目标PE，而不是直接照搬当前 Forward PE。
3) 计算关系必须显式写明：目标价 = Forward PE × EPS（此处 Forward PE 指 next year 视角下的目标PE区间，而非当前即时报价里的单点数值）。
4) EPS 仅使用 next_year_eps_forecast，若缺失则回退到 next_quarter_eps_forecast × 4，并必须标注“已回退口径”；若仍缺失，写“信息不足”。
5) 目标PE的确定必须基于三锚点并按固定权重：A/B/C 三锚点权重固定为 40% / 35% / 25%。
6) A 锚点规则：优先使用过去5年 Forward PE 均值，3年均值只用于校验均值回归方向。
7) B 锚点规则：PEG 修正采用 Bull/Base/Bear=1.4/1.2/1.0，并结合 next year 利润增速约束 PE 合理区间。
8) C 锚点规则：自动选取同业前3-5家可比公司做 Peer 对标。
9) 在加权结果上可做情绪修正，但情绪修正上限为 ±5%；Bull / Base / Bear 的 PE 偏移固定为 +15% / 0 / -15%。
10) 每只股票都必须给出 bull / base / bear 三种情景，且每个情景都包含：EPS口径、目标PE区间、目标价区间、关键假设（2-4条）。
11) 输出只展示最终目标PE区间，不展示A/B/C中间计算细节。
12) 估值和目标价只给区间，不需要精确到小数点；优先使用整数或整十区间表示。
13) 关键假设应围绕增速、利润率、估值倍数、行业景气、竞争格局与政策变量。
14) 若信息不足，明确写“信息不足”，并指出缺失数据项。
15) 全文中文，输出必须为 Markdown（不要 JSON/HTML）。
16) 给出“参考来源”，至少{min_sources}条，包含标题或机构名、日期、链接。

建议输出结构（每只股票都必须完整包含以下4行）：
### {{股票代码}}
- Bull 情景（乐观）: EPS口径=...；目标PE区间=...；目标价区间=...（目标价 = Forward PE × EPS）；关键假设=...
- Base 情景（中性）: EPS口径=...；目标PE区间=...；目标价区间=...（目标价 = Forward PE × EPS）；关键假设=...
- Bear 情景（保守）: EPS口径=...；目标PE区间=...；目标价区间=...（目标价 = Forward PE × EPS）；关键假设=...
- 情景结论:

## 参考来源

{search_block}
股票上下文：
{chr(10).join(blocks)}
""".strip()


def _build_ai_prompt(symbols, stocks, external_search_context=None, language="zh"):
    blocks = [_compact_stock_context(stock) for stock in stocks if stock.get("symbol") in symbols]
    if not blocks:
        return None

    today_utc = datetime.now(timezone.utc).date().isoformat()
    has_external_search = bool(str(external_search_context or "").strip())
    search_requirement_text = (
        "优先使用下方“外部搜索结果（由 Exa/Tavily 提供）”；不要再调用模型搜索工具。"
        if has_external_search
        else "必须调用模型搜索能力，补充最新新闻与研报观点；优先近30天信息。"
    )
    search_block = (
        f"\n外部搜索结果（由 Exa/Tavily 提供）：\n{str(external_search_context).strip()}\n"
        if has_external_search
        else ""
    )
    is_en = _is_english(language)

    if is_en:
        search_requirement_text_en = (
            "Prioritize external search results below (from Exa/Tavily); do not call model search tools again."
            if has_external_search
            else "Use model search to supplement latest news and research views, prioritizing the last 30 days."
        )
        search_block_en = (
            f"\nExternal search results (from Exa/Tavily):\n{str(external_search_context).strip()}\n"
            if has_external_search
            else ""
        )
        if len(symbols) <= 1:
            return f"""
You are a global equity research analyst. Provide an investment view for a single stock ({symbols[0] if symbols else ''}). Date (UTC): {today_utc}.
Core tasks:
- Combine macro/market context, sector trend, stock performance, financial quality, and latest news/research into a clear investment view.
- Focus on judgement and actionable view, not raw data copying.

Hard requirements:
1) Single-stock scenario only. Do not rank versus other stocks.
2) {search_requirement_text_en}
3) Cite only a few critical numbers to support conclusions.
4) Keep risk section to 1-2 items and include trigger path.
5) If information is missing, explicitly write "Information insufficient" and specify missing data.
6) Output must be English Markdown (no JSON/HTML).
7) Provide at least 3 references with title/institution, date, and link.

Recommended structure:
## Core conclusion
## Market and sector view
## Stock recommendation (3-6 months)
## Catalysts and validation signals
## Key risks (1-2)
## References

{search_block_en}
Stock context:
{chr(10).join(blocks)}
""".strip()

        return f"""
You are a global equity research analyst. Compare the following stocks and provide investment suggestions: {', '.join(symbols)}. Date (UTC): {today_utc}.
Core tasks:
- Combine macro/market context, sector trend, stock performance, financial quality, and latest news/research to produce multi-dimensional comparison and ranking.
- Focus on analytical judgement, not line-by-line data repetition.

Hard requirements:
1) {search_requirement_text_en}
2) Give overall judgement first, then rank investment conclusions (most preferred -> most cautious).
3) For each stock include: recommendation (Buy/Accumulate/Hold/Reduce), 3-6 month view, and 1-2 key risks.
4) Risk points must include trigger/impact path and stay concise.
5) Use limited key figures only; avoid numeric dumping.
6) If information is missing, explicitly write "Information insufficient" and specify missing data.
7) Output must be English Markdown (no JSON/HTML).
8) Provide at least 5 references with title/institution, date, and link.

Recommended structure:
## Core conclusion
## Ranked investment view (most preferred -> most cautious)
## Stock-by-stock analysis
## Catalysts and monitoring indicators (next 3-6 months)
## References

{search_block_en}
Stock context:
{chr(10).join(blocks)}
""".strip()

    if len(symbols) <= 1:
        return f"""
你是全球股票投研分析师。请对单只股票（{symbols[0] if symbols else ''}）给出投资建议。当前日期（UTC）: {today_utc}。
核心任务：
- 结合大盘环境、所属板块趋势、该股市场表现、财务质量、最新新闻/研报，形成研究结论。
- 重点是“判断与建议”，不是数据搬运；不要逐项复述输入里的表格数字。

硬性要求：
1) 单只股票场景，禁止做股票间对比；不要写“最看好/最不看好/排名”。
2) {search_requirement_text}
3) 可以引用少量关键数据来支撑观点，但避免堆砌。
4) 风险点只写1-2条，并写明触发条件或影响路径。
5) 若信息不足，明确写“信息不足”，并指出缺什么数据。
6) 全文中文，输出必须为 Markdown（不要 JSON/HTML）。
7) 给出“参考来源”，至少3条，包含标题或机构名、日期、链接。

建议输出结构（可微调，但不要缺项）：
## 核心结论
## 市场与板块判断
## 个股投资建议（3-6个月）
## 催化剂与验证信号
## 主要风险（1-2条）
## 参考来源

{search_block}
股票上下文：
{chr(10).join(blocks)}
""".strip()

    return f"""
你是全球股票投研分析师。请对以下股票做对比分析并给出投资建议：{', '.join(symbols)}。当前日期（UTC）: {today_utc}。
核心任务：
- 结合大盘环境、所属板块趋势、各股市场表现、财务质量、最新新闻/研报，做多维对比与排序建议。
- 重点是“分析判断”，不是逐行复述数据。

硬性要求：
1) {search_requirement_text}
2) 先给整体判断，再给投资建议结论排序（最看好 -> 最谨慎）。
3) 每只股票都要给：投资建议（买入/增持/观望/减持四选一）+ 3-6个月观点 + 主要风险（1-2条）。
4) 风险点不要写太多，每只仅1-2条，并写明触发条件或影响路径。
5) 可以引用少量关键数据支撑结论，但不要堆数字。
6) 若信息不足，明确写“信息不足”，并指出缺什么数据。
7) 全文中文，输出必须为 Markdown（不要 JSON/HTML）。
8) 给出“参考来源”，至少5条，包含标题或机构名、日期、链接。

建议输出结构（可微调，但不要缺项）：
## 核心观点综述
## 投资建议结论排序（最看好 -> 最谨慎）
## 个股详细分析
## 主要催化剂与观察指标（未来3-6个月）
## 参考来源

{search_block}
股票上下文：
{chr(10).join(blocks)}
""".strip()


def _normalize_followup_history(history, max_messages=None):
    if not isinstance(history, list):
        return []

    messages = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        messages.append({"role": role, "content": content})

    if isinstance(max_messages, int) and max_messages > 0:
        messages = messages[-max_messages:]
    return messages


def _format_followup_history_lines(history, language="zh"):
    normalized = _normalize_followup_history(history)
    if not normalized:
        return "- No follow-up history" if _is_english(language) else "- 无历史追问"
    lines = []
    is_en = _is_english(language)
    for msg in normalized:
        speaker = ("User" if msg.get("role") == "user" else "Assistant") if is_en else ("用户" if msg.get("role") == "user" else "助手")
        lines.append(f"{speaker}: {msg.get('content')}")
    return "\n".join(lines)


def _build_financial_followup_prompt(symbols, stocks, base_analysis, history, question, language="zh"):
    selected = _select_requested_stocks(symbols, stocks)
    if not selected:
        return None

    question_text = str(question or "").strip()
    if not question_text:
        return None

    today_utc = datetime.now(timezone.utc).date().isoformat()
    symbols_str = ", ".join(str(s.get("symbol")) for s in selected if s.get("symbol"))
    context_blocks = [_build_financial_analysis_stock_context(stock) for stock in selected]
    history_lines = _format_followup_history_lines(history, language=language)
    base_text = str(base_analysis or "").strip() or "无初始财务分析内容。"
    is_en = _is_english(language)

    if is_en:
        base_text_en = str(base_analysis or "").strip() or "No initial financial analysis content."
        return f"""
You are a global equity financial analyst handling a multi-turn follow-up for the "Financial Analysis" module. Date (UTC): {today_utc}.
Covered tickers: {symbols_str}

Answer rules:
1) Focus only on the latest question; avoid repeating the full original analysis.
2) Lead with conclusions and support with a few key facts/numbers.
3) If context is insufficient, explicitly write "Information insufficient" and state missing data.
4) If citing recent events/research, include references (title/institution, date, link).
5) Output in English Markdown (no JSON/HTML).

Initial financial analysis:
{base_text_en}

Conversation history:
{history_lines}

Latest question: {question_text}

Stock context:
{chr(10).join(context_blocks)}
""".strip()

    return f"""
你是全球股票财务分析专家，正在进行“财务分析”模块的多轮追问。当前日期（UTC）: {today_utc}。
覆盖股票: {symbols_str}

回答要求：
1) 只回答“最新追问”相关内容，避免重复整段初始分析。
2) 结论先行，并用少量关键数字或事实支撑判断。
3) 如果上下文不足，明确写“信息不足”，并指出需要补充的数据项。
4) 若引用最新事件/研报，请给出参考来源（标题或机构名、日期、链接）。
5) 输出中文 Markdown，不要 JSON/HTML。

初始财务分析回答:
{base_text}

历史对话:
{history_lines}

最新追问: {question_text}

股票上下文：
{chr(10).join(context_blocks)}
""".strip()


def _build_ai_followup_prompt(symbols, stocks, base_analysis, history, question, language="zh"):
    selected = _select_requested_stocks(symbols, stocks)
    if not selected:
        return None

    question_text = str(question or "").strip()
    if not question_text:
        return None

    today_utc = datetime.now(timezone.utc).date().isoformat()
    symbols_str = ", ".join(str(s.get("symbol")) for s in selected if s.get("symbol"))
    context_blocks = [_compact_stock_context(stock) for stock in selected]
    history_lines = _format_followup_history_lines(history, language=language)
    base_text = str(base_analysis or "").strip() or "无初始投资建议内容。"
    is_en = _is_english(language)

    if is_en:
        base_text_en = str(base_analysis or "").strip() or "No initial investment advice content."
        return f"""
You are a global equity research analyst handling a multi-turn follow-up for the "AI Investment Advice" module. Date (UTC): {today_utc}.
Covered tickers: {symbols_str}

Answer rules:
1) Focus only on the latest question; avoid repeating the full original advice.
2) Lead with conclusions, and add catalysts, validation signals, or risk triggers when needed.
3) If context is insufficient, explicitly write "Information insufficient" and state what is missing.
4) If discussing recent developments/news, provide references when possible (title/institution, date, link).
5) Output in English Markdown (no JSON/HTML).

Initial investment advice:
{base_text_en}

Conversation history:
{history_lines}

Latest question: {question_text}

Stock context:
{chr(10).join(context_blocks)}
""".strip()

    return f"""
你是全球股票投研分析师，正在进行“AI 投资建议”模块的多轮追问。当前日期（UTC）: {today_utc}。
覆盖股票: {symbols_str}

回答要求：
1) 只回答“最新追问”相关内容，避免重复整份初始建议。
2) 结论先行，必要时补充催化剂、验证信号或风险触发条件。
3) 信息不足时必须明确写“信息不足”，并说明缺失信息。
4) 若涉及最新动态/新闻，尽量补充参考来源（标题或机构名、日期、链接）。
5) 输出中文 Markdown，不要 JSON/HTML。

初始投资建议回答:
{base_text}

历史对话:
{history_lines}

最新追问: {question_text}

股票上下文：
{chr(10).join(context_blocks)}
""".strip()


def _generate_followup_response(prompt, stocks, provider, api_key, model, base_url=None, language="zh"):
    lang = _normalize_ui_language(language)
    if not api_key:
        raise _service_error(
            code="AI_API_KEY_MISSING",
            language=lang,
            zh_text="未配置 AI API Key，无法继续追问。",
            en_text="AI API key is not configured; unable to continue.",
            status_code=400,
        )
    if not model:
        raise _service_error(
            code="AI_MODEL_MISSING",
            language=lang,
            zh_text="未配置 AI 模型名，无法继续追问。",
            en_text="AI model is not configured; unable to continue.",
            status_code=400,
        )
    if not prompt:
        raise _service_error(
            code="STOCK_CONTEXT_MISSING",
            language=lang,
            zh_text="缺少可分析的股票上下文，无法继续追问。",
            en_text="Missing stock context; unable to continue.",
            status_code=400,
        )

    full_text, err = _run_ai_with_auto_continue(
        provider=provider,
        prompt=prompt,
        api_key=api_key,
        model=model,
        base_url=base_url,
        enable_model_search=True,
        continue_prompt=(
            "Continue only the unfinished part. Do not repeat previous text."
            if lang == "en"
            else "继续未完成的部分，只补充未输出内容，不要重复前文。"
        ),
        language=lang,
    )
    if err:
        raise _runtime_ai_error_to_service_error(err, lang)
    if not full_text:
        raise _service_error(
            code="AI_EMPTY_RESPONSE",
            language=lang,
            zh_text="AI 返回为空。",
            en_text="AI returned empty content.",
            status_code=502,
        )
    return _ensure_reference_links(full_text, stocks=stocks)


def generate_financial_analysis_followup(
    symbols,
    stocks,
    provider,
    api_key,
    model,
    question,
    base_analysis=None,
    history=None,
    base_url=None,
    language="zh",
):
    lang = _normalize_ui_language(language)
    prompt = _build_financial_followup_prompt(
        symbols=symbols,
        stocks=stocks,
        base_analysis=base_analysis,
        history=history,
        question=question,
        language=lang,
    )
    return _generate_followup_response(
        prompt=prompt,
        stocks=stocks,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        language=lang,
    )


def generate_ai_investment_followup(
    symbols,
    stocks,
    provider,
    api_key,
    model,
    question,
    base_analysis=None,
    history=None,
    base_url=None,
    language="zh",
):
    lang = _normalize_ui_language(language)
    prompt = _build_ai_followup_prompt(
        symbols=symbols,
        stocks=stocks,
        base_analysis=base_analysis,
        history=history,
        question=question,
        language=lang,
    )
    return _generate_followup_response(
        prompt=prompt,
        stocks=stocks,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        language=lang,
    )


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


def _call_gemini_once(prompt, api_key, model, enable_model_search=True):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    base_payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4},
    }

    if not enable_model_search:
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=base_payload,
            timeout=AI_PROVIDER_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    else:
        # 优先开启 Gemini 搜索能力以获取更实时的新闻/研报信息。
        payload_with_search = {**base_payload, "tools": [{"google_search": {}}]}

        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload_with_search,
                timeout=AI_PROVIDER_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError as exc:
            # 某些模型不支持 google_search 工具时，自动回退到普通调用。
            status = exc.response.status_code if exc.response is not None else None
            if status not in {400, 404}:
                raise
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=base_payload,
                timeout=AI_PROVIDER_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()

    candidates = data.get("candidates", [])
    if not candidates:
        return "", ""
    first = candidates[0]
    parts = first.get("content", {}).get("parts", [])
    texts = [p.get("text", "") for p in parts if p.get("text")]
    return "\n".join(texts).strip(), str(first.get("finishReason", "")).lower()


def _call_openai_compatible_once(prompt, api_key, model, base_url, language="zh"):
    root = (base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{root}/chat/completions"
    is_en = _is_english(language)
    system_text = (
        "You are a senior global equity analyst. Respond in English with clear structure and actionable conclusions. "
        "Prioritize analytical judgement over mechanical data repetition. Keep each stock's key risk points to at most two. "
        "Output Markdown only. Do not output JSON/HTML or extra meta commentary."
        if is_en
        else (
            "你是资深全球股票分析师，回答要中文、结构清晰、可执行。"
            "以研究判断为主，不要机械复述原始数据。"
            "个股观点要全面，但每只股票风险点最多2条。"
            "最终只输出 Markdown，不要输出 JSON、HTML 或额外解释。"
        )
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_text,
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=AI_PROVIDER_TIMEOUT_SECONDS,
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
        "max_tokens": AI_CLAUDE_MAX_TOKENS,
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
        timeout=AI_PROVIDER_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("content", [])
    texts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            texts.append(str(item.get("text")))
    return "\n".join(texts).strip(), str(data.get("stop_reason", "")).lower()


def _call_ai_once(provider_key, prompt, api_key, model, base_url=None, enable_model_search=True, language="zh"):
    if provider_key == "gemini":
        return _call_gemini_once(prompt, api_key, model, enable_model_search=enable_model_search)
    if provider_key == "claude":
        return _call_claude_once(prompt, api_key, model)
    if provider_key == "openai":
        return _call_openai_compatible_once(prompt, api_key, model, base_url, language=language)
    raise ValueError(f"不支持的 AI Provider: {provider_key}")


def _call_ai_once_with_search_flag(
    provider_key,
    prompt,
    api_key,
    model,
    base_url=None,
    enable_model_search=True,
    language="zh",
):
    try:
        return _call_ai_once(
            provider_key,
            prompt,
            api_key,
            model,
            base_url,
            enable_model_search=enable_model_search,
            language=language,
        )
    except TypeError as exc:
        # 测试替身可能仍使用旧签名，不接受 enable_model_search。
        if "enable_model_search" not in str(exc) and "language" not in str(exc):
            raise
        try:
            return _call_ai_once(provider_key, prompt, api_key, model, base_url, enable_model_search=enable_model_search)
        except TypeError as nested_exc:
            if "enable_model_search" not in str(nested_exc):
                raise
            return _call_ai_once(provider_key, prompt, api_key, model, base_url)


def _is_truncated_reason(reason):
    r = (reason or "").lower()
    return r in {"length", "max_tokens", "token_limit", "max_output_tokens", "model_length"}


def _run_ai_with_auto_continue(
    provider,
    prompt,
    api_key,
    model,
    base_url=None,
    enable_model_search=True,
    continue_prompt="继续未完成的部分，只补充未输出内容，不要重复前文。",
    language="zh",
):
    provider_key = (provider or "").strip().lower()
    lang = _normalize_ui_language(language)
    if provider_key not in {"openai", "gemini", "claude"}:
        return "", (f"Unsupported AI provider: {provider}" if lang == "en" else f"不支持的 AI Provider: {provider}")

    full_text = ""
    next_prompt = str(prompt or "").strip()
    if not next_prompt:
        return "", ("Missing stock context for analysis." if lang == "en" else "缺少可分析的股票上下文。")

    try:
        for _ in range(AI_AUTO_CONTINUE_MAX_ROUNDS):
            try:
                text, finish_reason = _call_ai_once_with_search_flag(
                    provider_key,
                    next_prompt,
                    api_key,
                    model,
                    base_url,
                    enable_model_search=enable_model_search,
                    language=lang,
                )
            except TypeError as exc:
                if "language" not in str(exc):
                    raise
                text, finish_reason = _call_ai_once_with_search_flag(
                    provider_key,
                    next_prompt,
                    api_key,
                    model,
                    base_url,
                    enable_model_search=enable_model_search,
                )
            text = (text or "").strip()
            if text:
                full_text = (full_text + "\n\n" + text).strip() if full_text else text

            if not _is_truncated_reason(finish_reason):
                break
            next_prompt = continue_prompt
    except Exception as exc:
        return "", (f"AI call failed: {exc}" if lang == "en" else f"AI 调用失败: {exc}")

    return full_text.strip(), None


def generate_ai_investment_advice(
    symbols,
    stocks,
    provider,
    api_key,
    model,
    base_url=None,
    exa_api_key=None,
    tavily_api_key=None,
    language="zh",
):
    lang = _normalize_ui_language(language)
    if not api_key:
        raise _service_error(
            code="AI_API_KEY_MISSING",
            language=lang,
            zh_text="未配置 AI API Key，无法生成投资建议。",
            en_text="AI API key is not configured; unable to generate investment advice.",
            status_code=400,
        )
    if not model:
        raise _service_error(
            code="AI_MODEL_MISSING",
            language=lang,
            zh_text="未配置 AI 模型名，无法生成投资建议。",
            en_text="AI model is not configured; unable to generate investment advice.",
            status_code=400,
        )

    external_search_context = _build_external_search_context(
        symbols=symbols,
        mode="ai",
        exa_api_key=exa_api_key,
        tavily_api_key=tavily_api_key,
        lookback_days=30,
    )
    prompt = _build_ai_prompt(symbols, stocks, external_search_context=external_search_context, language=lang)
    if not prompt:
        raise _service_error(
            code="STOCK_CONTEXT_MISSING",
            language=lang,
            zh_text="缺少可分析的股票上下文，无法生成建议。",
            en_text="Missing stock context; unable to generate advice.",
            status_code=400,
        )

    full_text, err = _run_ai_with_auto_continue(
        provider=provider,
        prompt=prompt,
        api_key=api_key,
        model=model,
        base_url=base_url,
        enable_model_search=not bool(str(external_search_context or "").strip()),
        continue_prompt=(
            (
                "Your previous answer was truncated by output length. Continue only the unfinished part, "
                "do not repeat prior content, and complete the final closing."
            )
            if lang == "en"
            else (
                "你刚才的回答因为长度限制被截断了。请只继续未完成的部分，"
                "不要重复已经写过的内容，并写到完整收尾。"
            )
        ),
        language=lang,
    )
    if err:
        raise _runtime_ai_error_to_service_error(err, lang)
    if not full_text:
        raise _service_error(
            code="AI_EMPTY_RESPONSE",
            language=lang,
            zh_text="AI 返回为空。",
            en_text="AI returned empty content.",
            status_code=502,
        )
    return _ensure_reference_links(full_text, stocks=stocks)


def generate_target_price_analysis(
    symbols,
    stocks,
    provider,
    api_key,
    model,
    base_url=None,
    exa_api_key=None,
    tavily_api_key=None,
    language="zh",
):
    lang = _normalize_ui_language(language)
    if not api_key:
        raise _service_error(
            code="AI_API_KEY_MISSING",
            language=lang,
            zh_text="未配置 AI API Key，无法生成目标价分析。",
            en_text="AI API key is not configured; unable to generate target price analysis.",
            status_code=400,
        )
    if not model:
        raise _service_error(
            code="AI_MODEL_MISSING",
            language=lang,
            zh_text="未配置 AI 模型名，无法生成目标价分析。",
            en_text="AI model is not configured; unable to generate target price analysis.",
            status_code=400,
        )

    external_search_context = _build_external_search_context(
        symbols=symbols,
        mode="ai",
        exa_api_key=exa_api_key,
        tavily_api_key=tavily_api_key,
        lookback_days=45,
    )
    prompt = _build_target_price_prompt(symbols, stocks, external_search_context=external_search_context, language=lang)
    if not prompt:
        raise _service_error(
            code="STOCK_CONTEXT_MISSING",
            language=lang,
            zh_text="缺少可分析的股票上下文，无法生成目标价分析。",
            en_text="Missing stock context; unable to generate target price analysis.",
            status_code=400,
        )

    full_text, err = _run_ai_with_auto_continue(
        provider=provider,
        prompt=prompt,
        api_key=api_key,
        model=model,
        base_url=base_url,
        enable_model_search=not bool(str(external_search_context or "").strip()),
        continue_prompt=(
            (
                "Your previous answer was truncated by output length. Continue only the unfinished part, "
                "do not repeat prior content, and complete the final closing."
            )
            if lang == "en"
            else (
                "你刚才的回答因为长度限制被截断了。请只继续未完成的部分，"
                "不要重复已经写过的内容，并写到完整收尾。"
            )
        ),
        language=lang,
    )
    if err:
        raise _runtime_ai_error_to_service_error(err, lang)
    if not full_text:
        raise _service_error(
            code="AI_EMPTY_RESPONSE",
            language=lang,
            zh_text="AI 返回为空。",
            en_text="AI returned empty content.",
            status_code=502,
        )
    return _ensure_reference_links(full_text, stocks=stocks)


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


def test_exa_api_key(api_key):
    key = str(api_key or "").strip()
    if not key:
        return False, "请填写 Exa API Key。"
    try:
        results = _search_with_exa(
            query="NVIDIA earnings guidance latest",
            api_key=key,
            max_results=1,
            lookback_days=3650,
        )
        return (True, "Exa 配置可用。") if results else (False, "Exa 返回为空，请检查 Key 或权限。")
    except Exception as exc:
        return False, f"Exa 测试失败: {exc}"


def test_tavily_api_key(api_key):
    key = str(api_key or "").strip()
    if not key:
        return False, "请填写 Tavily API Key。"
    try:
        results = _search_with_tavily(
            query="NVIDIA earnings guidance latest",
            api_key=key,
            max_results=1,
            lookback_days=3650,
        )
        return (True, "Tavily 配置可用。") if results else (False, "Tavily 返回为空，请检查 Key 或权限。")
    except Exception as exc:
        return False, f"Tavily 测试失败: {exc}"





