from pathlib import Path
import subprocess

import app


def test_parse_symbols_empty_returns_empty_list():
    assert app.parse_symbols("") == []
    assert app.parse_symbols(" , , ") == []


def test_index_renders_empty_default_symbols():
    client = app.app.test_client()
    resp = client.get("/")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="symbols"' in html
    assert 'value=""' in html


def test_frontend_init_has_no_nvda_and_no_auto_fetch():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert '|| "NVDA"' not in js
    assert "fetchCompare().catch" not in js
    assert "const defaults = parseSymbols(document.getElementById(\"symbols\").value);" in js
    assert "await loadWatchlist(defaults.length === 0);" not in js


def test_frontend_does_not_require_finnhub_key_for_compare_or_export():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert "if (!cfg.finnhubApiKey) {" not in js
    assert 'if (cfg.finnhubApiKey) headers["X-Finnhub-Api-Key"] = cfg.finnhubApiKey;' in js


def test_frontend_js_has_valid_syntax():
    result = subprocess.run(
        ["node", "--check", "static/app.js"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_frontend_text_is_not_mojibake():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert "股价 (USD)" in js
    assert "添加股票" in js
    assert "请先添加至少1个股票代码。" in js
    assert "正在抓取股票数据..." in js
    assert "璇峰厛" not in js


def test_frontend_status_time_uses_formatted_display():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert 'status.textContent = `数据更新时间: ${fmtTime(data.generated_at)}`;' in js


def test_forecast_table_includes_ev_ebitda_and_ps_columns():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert '["ev_to_ebitda", "EV/EBITDA"]' in js
    assert '["ps", "P/S"]' in js
    assert '["pb", "P/B"]' in js


def test_forecast_table_uses_valuation_only_columns():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert '["forward_pe", "Forward PE"]' in js
    assert '["peg", "PEG(5yr expected)"]' in js
    assert '["ev_to_ebitda", "EV/EBITDA"]' in js
    assert '["ps", "P/S"]' in js
    assert '["pb", "P/B"]' in js


def test_prediction_table_contains_yfinance_eps_and_earnings_date_fields():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert "prediction: (stock && stock.forecast && typeof stock.forecast === \"object\") ? stock.forecast : {}" in js
    assert "预测EPS(Current Year)" in js
    assert "预测EPS(Next Year)" in js
    assert "预测EPS(Next Quarter)" in js
    assert "下季度财报日期" in js


def test_template_has_collapsible_beat_miss_and_eps_trend_sections():
    html = Path("templates/index.html").read_text(encoding="utf-8")

    assert 'class="insight-panel"' in html
    assert "财报 beat/miss、历史 EPS surprise（点击展开）" in html
    assert "一致预期变化 EPS Trend（7/30/60/90天）（点击展开）" in html


def test_template_has_target_price_section_after_ai_analysis():
    html = Path("templates/index.html").read_text(encoding="utf-8")

    idx_valuation = html.find("<h2>4) 估值</h2>")
    idx_financial = html.find("<h2>5) 财务分析</h2>")
    idx_ai = html.find("<h2>6) 投资建议</h2>")
    idx_target_price = html.find("<h2>7) 目标价</h2>")

    assert idx_valuation >= 0
    assert idx_financial > idx_valuation
    assert idx_ai > idx_financial
    assert idx_target_price > idx_ai
    assert 'id="target-price-btn"' in html
    assert 'id="target-price-output"' in html


def test_frontend_links_are_rendered_as_plain_text():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert "output.querySelectorAll(\"a\")" in js
    assert "a.replaceWith(replacement)" in js
    assert "a.setAttribute(\"target\", \"_blank\")" not in js


def test_frontend_strips_reference_section_before_rendering():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert "function stripReferenceSection(markdownText)" in js
    assert "参考来源" in js
    assert "const cleaned = stripReferenceSection(markdownText);" in js
    assert "renderMarkdownOutput(\"ai-output\", cleaned, \"无返回内容\")" in js
    assert "renderMarkdownOutput(\"earnings-output\", cleaned, emptyText)" in js


def test_frontend_has_search_api_test_buttons():
    html = Path("templates/index.html").read_text(encoding="utf-8")

    assert 'id="test-exa-btn"' in html
    assert 'id="test-tavily-btn"' in html


def test_frontend_can_test_search_api_config():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert "async function testExaConfig()" in js
    assert "async function testTavilyConfig()" in js
    assert 'target: "exa"' in js
    assert 'target: "tavily"' in js
    assert "test-exa-btn" in js
    assert "test-tavily-btn" in js


def test_capture_screen_disables_effects_for_readability():
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert "onclone: (clonedDoc) => {" in js
    assert "animation: none !important;" in js
    assert "backdrop-filter: none !important;" in js
    assert "clonedStatus.style.display = \"none\";" in js
