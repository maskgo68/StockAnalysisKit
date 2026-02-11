const state = {
  symbols: [],
  stocks: [],
  stockErrors: [],
  compareErrorsDismissed: false,
  uiLanguage: "zh",
  watchlist: {
    items: [],
    refreshedAt: null
  },
  analysis: {
    targetPrice: "",
    earnings: "",
    ai: ""
  },
  followups: {
    earnings: [],
    ai: []
  },
  followupLoading: {
    earnings: false,
    ai: false
  }
};

const storageKeys = {
  uiLanguage: "stockanalysiskit.ui_language",
  finnhubApiKey: "stockanalysiskit.finnhub_api_key",
  aiProvider: "stockanalysiskit.ai_provider",
  aiModel: "stockanalysiskit.ai_model",
  aiApiKey: "stockanalysiskit.ai_api_key",
  aiBaseUrl: "stockanalysiskit.ai_base_url",
  exaApiKey: "stockanalysiskit.exa_api_key",
  tavilyApiKey: "stockanalysiskit.tavily_api_key"
};

const defaultModels = {
  openai: "gpt-4.1-mini",
  gemini: "gemini-2.0-flash",
  claude: "claude-3-5-sonnet-latest"
};

const i18n = {
  zh: {
    document_title: "股票分析助手",
    lang_toggle: "EN",
    hero_title: "股票分析助手",
    hero_hint: "数据源：第1部分 Finnhub 优先（无 API Key 或数据缺失时回退 yfinance），第2/3部分 yfinance（最新财务、预测）；其后补充模块 yfinance（beat/miss 与 EPS Trend）；第4部分 Yahoo Finance 接口/页面解析（估值字段为主）。金额字段按各股票对应币种展示，带“十亿”字样的字段单位为十亿。",
    hero_tag_1: "Realtime Market",
    hero_tag_2: "Financial Cache",
    hero_tag_3: "AI Research Notes",
    add_symbol_label: "添加股票代码",
    add_symbol_placeholder: "例如 NVDA、0700.HK、600519.SS",
    add_symbol_btn: "添加股票",
    watchlist_title: "自选股组合",
    watchlist_empty: "暂无已保存自选组",
    watchlist_name_placeholder: "输入自选组名称（可选）",
    watchlist_save_btn: "保存当前自选",
    watchlist_refresh_btn: "刷新自选列表",
    refresh_btn: "刷新数据",
    force_refresh_btn: "强制刷新财务缓存",
    export_btn: "导出Excel",
    screenshot_btn: "截屏下载",
    section_realtime: "1) 实时行情",
    section_financial: "2) 最新财务数据",
    section_prediction: "3) 预测",
    beat_miss_summary: "财报 beat/miss、历史 EPS surprise（点击展开）",
    beat_miss_empty: "请先抓取数据，再查看历史超预期表现。",
    eps_trend_summary: "一致预期变化 EPS Trend（7/30/60/90天）（点击展开）",
    eps_trend_empty: "请先抓取数据，再查看一致预期变化趋势。",
    section_valuation: "4) 估值",
    section_earnings: "5) 财务分析",
    generate_earnings_btn: "生成财务分析",
    copy_btn: "复制输出",
    earnings_initial_empty: "请先抓取数据，再生成财务分析。",
    earnings_followup_placeholder: "继续追问财务分析，例如：AI业务收入占比是多少？",
    followup_send_btn: "发送追问",
    earnings_followup_empty: "财务分析生成后可继续追问。",
    section_ai: "6) 投资建议",
    generate_ai_btn: "生成 AI 综合建议",
    ai_initial_empty: "请先抓取数据，再生成建议。",
    ai_followup_placeholder: "继续追问投资建议，例如：竞争对手 AMD 最新动态？",
    ai_followup_empty: "AI 建议生成后可继续追问。",
    section_target_price: "7) 目标价",
    generate_target_btn: "生成目标价分析",
    target_initial_empty: "请先抓取数据，再生成目标价分析。",
    api_config_title: "API 配置与测试",
    api_config_hint: "点击展开/收起",
    finnhub_key_label: "Finnhub API Key（可选）",
    finnhub_key_placeholder: "可选：用于第1部分实时行情优先数据源",
    ai_provider_label: "AI Provider",
    ai_provider_openai: "OpenAI 兼容",
    ai_model_label: "AI 模型",
    ai_model_placeholder: "例如 gpt-4.1-mini",
    ai_base_url_label: "OpenAI 兼容 Base URL",
    ai_base_url_placeholder: "默认 https://api.openai.com/v1",
    ai_base_url_placeholder_non_openai: "仅 OpenAI 兼容 Provider 需要",
    ai_api_key_label: "AI API Key",
    ai_api_key_placeholder: "粘贴 AI Key",
    exa_api_key_label: "Exa API Key（可选）",
    tavily_api_key_label: "Tavily API Key（可选）",
    search_key_placeholder: "可选：用于外部搜索增强",
    test_finnhub_btn: "测试 Finnhub 配置",
    test_ai_btn: "测试 AI 配置",
    test_exa_btn: "测试 Exa 配置",
    test_tavily_btn: "测试 Tavily 配置",
    table_metric: "指标",
    chip_empty: "请先添加股票代码",
    remove: "删除",
    watchlist_saved_meta: "已保存{{count}}组 ({{time}})",
    watchlist_unknown_name: "未命名",
    watchlist_load_btn: "加载",
    watchlist_rename_btn: "重命名",
    watchlist_delete_btn: "删除",
    err_load_watchlist: "加载自选组失败: {{status}}",
    err_save_watchlist: "保存自选组失败: {{status}}",
    err_need_watchlist_symbol: "请先添加至少1个股票代码后再保存。",
    err_empty_watchlist: "该自选组为空，无法加载。",
    err_delete_watchlist: "删除自选组失败: {{status}}",
    err_watchlist_not_found: "删除失败：自选组不存在。",
    err_rename_watchlist: "修改自选组名称失败: {{status}}",
    markdown_empty: "无返回内容",
    followup_you: "你",
    reference_header: "参考来源",
    target_label: "目标价分析",
    earnings_label: "财务分析",
    ai_label: "AI投资建议",
    err_copy_manual: "复制失败，请手动复制",
    err_copy_no_content: "暂无可复制的{{label}}内容",
    status_copied: "{{label}}已复制到剪贴板",
    latest_period_quarterly: "季度",
    latest_period_annual: "年度",
    beat_miss_panel_title: "财报 beat/miss、历史 EPS surprise",
    beat_miss_line_latest: "- 最新财报: {{latest_quarter}} | EPS实际={{eps_actual}} | EPS预期={{eps_estimate}} | Surprise={{surprise}} | 结果={{result}}",
    beat_miss_line_recent: "- 近4季 surprise: {{surprises}}；Beat={{beat}}，Miss={{miss}}，连续Beat={{streak}}",
    beat_miss_line_conclusion: "- 结论: {{conclusion}}",
    eps_trend_panel_title: "一致预期变化 EPS Trend（7/30/60/90天）",
    eps_trend_line_basis: "- 口径: {{period}} | current={{current}} | 7d={{d7}} | 30d={{d30}} | 60d={{d60}} | 90d={{d90}}",
    eps_trend_line_change: "- 变化: vs30d={{vs30}}，vs90d={{vs90}} | signal={{signal}}",
    eps_trend_line_conclusion: "- 结论: {{conclusion}}",
    info_insufficient: "信息不足",
    beat_miss_no_data: "暂无可用 beat/miss 数据。",
    eps_trend_no_data: "暂无可用 EPS Trend 数据。",
    err_need_symbol: "请先添加至少1个股票代码。",
    status_fetching: "正在抓取股票数据...",
    status_fetching_force: "正在抓取股票数据（强制刷新财务缓存）...",
    err_api_failed: "接口失败: {{status}}",
    prompt_generate_target: "请点击“生成目标价分析”。",
    prompt_generate_earnings: "请点击“生成财务分析”。",
    prompt_generate_ai: "请点击“生成 AI 综合建议”。",
    status_data_time: "数据更新时间: {{time}}",
    compare_partial_failed: "部分股票抓取失败（{{count}}）",
    compare_error_panel_title: "抓取失败明细（{{count}}）",
    compare_error_dismiss_btn: "关闭提醒",
    err_need_fetch_data: "请先抓取数据。",
    err_need_ai_config: "请先填写 AI API Key 和模型。",
    target_generating: "目标价分析生成中，请稍候...",
    status_target_generating: "正在生成目标价分析...",
    action_failed: "生成失败: {{status}}",
    status_target_done_with_model: "目标价分析已生成（{{provider}} / {{model}}）",
    status_target_done: "目标价分析已生成",
    earnings_generating: "财务分析生成中，请稍候...",
    status_earnings_generating_ai: "正在生成财务分析（AI增强）...",
    status_earnings_generating: "正在生成财务分析...",
    status_earnings_done_with_model: "财务分析已生成（{{provider}} / {{model}}）",
    status_earnings_done: "财务分析已生成",
    ai_generating: "AI 分析中，请稍候...",
    status_ai_generating: "正在调用 AI...",
    ai_model_status: "AI模型: {{provider}} / {{model}}",
    err_followup_empty: "请输入追问内容。",
    err_followup_need_base: "请先生成对应的 AI 分析，再进行追问。",
    followup_status_earnings_loading: "正在追问财务分析...",
    followup_status_earnings_done: "财务分析追问已更新",
    followup_status_ai_loading: "正在追问 AI 建议...",
    followup_status_ai_done: "AI 建议追问已更新",
    followup_failed: "追问失败: {{status}}",
    followup_failed_prefix: "追问失败：{{message}}",
    export_failed: "导出失败: {{status}}",
    status_testing_finnhub: "正在测试 Finnhub 配置...",
    status_test_finnhub_done: "Finnhub 测试完成",
    status_testing_ai: "正在测试 AI 配置...",
    status_test_ai_done: "AI 测试完成",
    status_testing_exa: "正在测试 Exa 配置...",
    status_test_exa_done: "Exa 测试完成",
    status_testing_tavily: "正在测试 Tavily 配置...",
    status_test_tavily_done: "Tavily 测试完成",
    status_capturing: "正在生成截屏...",
    err_capture_lib: "截屏库未加载，请刷新页面后重试。",
    status_capture_done: "截屏已下载。",
    capture_failed: "截屏失败: {{message}}",
    status_watchlist_saved: "自选组已保存。",
    status_watchlist_refreshed: "自选组列表已刷新。",
    status_watchlist_loaded: "自选组已加载。",
    prompt_watchlist_rename: "请输入新的自选组名称",
    err_watchlist_name_empty: "自选组名称不能为空",
    status_watchlist_renamed: "自选组已改名为 {{name}}",
    status_watchlist_deleted: "自选组已删除。"
  },
  en: {
    document_title: "Stock Analysis Assistant",
    lang_toggle: "中文",
    hero_title: "Stock Analysis Assistant",
    hero_hint: "Data sources: Part 1 uses Finnhub first (falls back to yfinance if API key is missing or data is unavailable). Parts 2/3 use yfinance (latest financials and forecasts). Additional modules use yfinance (beat/miss and EPS trend). Part 4 uses Yahoo Finance API/page parsing (valuation focused). Monetary fields are displayed in each stock's native currency; fields with “B” are in billions.",
    hero_tag_1: "Realtime Market",
    hero_tag_2: "Financial Cache",
    hero_tag_3: "AI Research Notes",
    add_symbol_label: "Add Ticker Symbol",
    add_symbol_placeholder: "e.g. NVDA, 0700.HK, 600519.SS",
    add_symbol_btn: "Add Stock",
    watchlist_title: "Watchlist Sets",
    watchlist_empty: "No saved watchlists yet",
    watchlist_name_placeholder: "Watchlist name (optional)",
    watchlist_save_btn: "Save Current",
    watchlist_refresh_btn: "Refresh List",
    refresh_btn: "Refresh Data",
    force_refresh_btn: "Force Financial Refresh",
    export_btn: "Export Excel",
    screenshot_btn: "Download Screenshot",
    section_realtime: "1) Realtime Market",
    section_financial: "2) Latest Financial Data",
    section_prediction: "3) Forecast",
    beat_miss_summary: "Earnings beat/miss and historical EPS surprises (click to expand)",
    beat_miss_empty: "Fetch data first, then view historical surprise performance.",
    eps_trend_summary: "Consensus EPS trend changes (7/30/60/90 days) (click to expand)",
    eps_trend_empty: "Fetch data first, then view consensus EPS trend changes.",
    section_valuation: "4) Valuation",
    section_earnings: "5) Financial Analysis",
    generate_earnings_btn: "Generate Financial Analysis",
    copy_btn: "Copy Output",
    earnings_initial_empty: "Fetch data first, then generate financial analysis.",
    earnings_followup_placeholder: "Ask a follow-up on financial analysis, e.g. What's AI revenue mix?",
    followup_send_btn: "Send Follow-up",
    earnings_followup_empty: "Follow-ups are available after financial analysis is generated.",
    section_ai: "6) Investment Advice",
    generate_ai_btn: "Generate AI Composite Advice",
    ai_initial_empty: "Fetch data first, then generate advice.",
    ai_followup_placeholder: "Ask a follow-up on investment advice, e.g. Latest AMD developments?",
    ai_followup_empty: "Follow-ups are available after AI advice is generated.",
    section_target_price: "7) Target Price",
    generate_target_btn: "Generate Target Price Analysis",
    target_initial_empty: "Fetch data first, then generate target price analysis.",
    api_config_title: "API Config & Tests",
    api_config_hint: "Click to expand/collapse",
    finnhub_key_label: "Finnhub API Key (Optional)",
    finnhub_key_placeholder: "Optional: preferred source for Part 1 realtime market data",
    ai_provider_label: "AI Provider",
    ai_provider_openai: "OpenAI Compatible",
    ai_model_label: "AI Model",
    ai_model_placeholder: "e.g. gpt-4.1-mini",
    ai_base_url_label: "OpenAI Compatible Base URL",
    ai_base_url_placeholder: "Default https://api.openai.com/v1",
    ai_base_url_placeholder_non_openai: "Only required for OpenAI-compatible providers",
    ai_api_key_label: "AI API Key",
    ai_api_key_placeholder: "Paste AI key",
    exa_api_key_label: "Exa API Key (Optional)",
    tavily_api_key_label: "Tavily API Key (Optional)",
    search_key_placeholder: "Optional: used for external search enhancement",
    test_finnhub_btn: "Test Finnhub Config",
    test_ai_btn: "Test AI Config",
    test_exa_btn: "Test Exa Config",
    test_tavily_btn: "Test Tavily Config",
    table_metric: "Metric",
    chip_empty: "Add at least one symbol first",
    remove: "Remove",
    watchlist_saved_meta: "{{count}} saved set(s) ({{time}})",
    watchlist_unknown_name: "Untitled",
    watchlist_load_btn: "Load",
    watchlist_rename_btn: "Rename",
    watchlist_delete_btn: "Delete",
    err_load_watchlist: "Failed to load watchlists: {{status}}",
    err_save_watchlist: "Failed to save watchlist: {{status}}",
    err_need_watchlist_symbol: "Add at least one symbol before saving.",
    err_empty_watchlist: "This watchlist is empty and cannot be loaded.",
    err_delete_watchlist: "Failed to delete watchlist: {{status}}",
    err_watchlist_not_found: "Delete failed: watchlist not found.",
    err_rename_watchlist: "Failed to rename watchlist: {{status}}",
    markdown_empty: "No content returned",
    followup_you: "You",
    reference_header: "References",
    target_label: "Target Price Analysis",
    earnings_label: "Financial Analysis",
    ai_label: "AI Investment Advice",
    err_copy_manual: "Copy failed, please copy manually",
    err_copy_no_content: "No {{label}} content to copy",
    status_copied: "{{label}} copied to clipboard",
    latest_period_quarterly: "Quarterly",
    latest_period_annual: "Annual",
    beat_miss_panel_title: "Earnings beat/miss and historical EPS surprises",
    beat_miss_line_latest: "- Latest report: {{latest_quarter}} | EPS actual={{eps_actual}} | EPS estimate={{eps_estimate}} | Surprise={{surprise}} | Result={{result}}",
    beat_miss_line_recent: "- Last 4Q surprises: {{surprises}}; Beat={{beat}}, Miss={{miss}}, Beat streak={{streak}}",
    beat_miss_line_conclusion: "- Conclusion: {{conclusion}}",
    eps_trend_panel_title: "Consensus EPS trend changes (7/30/60/90 days)",
    eps_trend_line_basis: "- Basis: {{period}} | current={{current}} | 7d={{d7}} | 30d={{d30}} | 60d={{d60}} | 90d={{d90}}",
    eps_trend_line_change: "- Change: vs30d={{vs30}}, vs90d={{vs90}} | signal={{signal}}",
    eps_trend_line_conclusion: "- Conclusion: {{conclusion}}",
    info_insufficient: "Information insufficient",
    beat_miss_no_data: "No beat/miss data available.",
    eps_trend_no_data: "No EPS trend data available.",
    err_need_symbol: "Add at least one symbol first.",
    status_fetching: "Fetching stock data...",
    status_fetching_force: "Fetching stock data (force financial refresh)...",
    err_api_failed: "API request failed: {{status}}",
    prompt_generate_target: "Click “Generate Target Price Analysis”.",
    prompt_generate_earnings: "Click “Generate Financial Analysis”.",
    prompt_generate_ai: "Click “Generate AI Composite Advice”.",
    status_data_time: "Data updated at: {{time}}",
    compare_partial_failed: "Partial fetch failures ({{count}})",
    compare_error_panel_title: "Fetch errors ({{count}})",
    compare_error_dismiss_btn: "Dismiss",
    err_need_fetch_data: "Fetch data first.",
    err_need_ai_config: "Please fill in AI API key and model first.",
    target_generating: "Generating target price analysis, please wait...",
    status_target_generating: "Generating target price analysis...",
    action_failed: "Generation failed: {{status}}",
    status_target_done_with_model: "Target price analysis generated ({{provider}} / {{model}})",
    status_target_done: "Target price analysis generated",
    earnings_generating: "Generating financial analysis, please wait...",
    status_earnings_generating_ai: "Generating financial analysis (AI enhanced)...",
    status_earnings_generating: "Generating financial analysis...",
    status_earnings_done_with_model: "Financial analysis generated ({{provider}} / {{model}})",
    status_earnings_done: "Financial analysis generated",
    ai_generating: "Generating AI analysis, please wait...",
    status_ai_generating: "Calling AI...",
    ai_model_status: "AI model: {{provider}} / {{model}}",
    err_followup_empty: "Please enter a follow-up question.",
    err_followup_need_base: "Generate the related AI analysis first before follow-up.",
    followup_status_earnings_loading: "Asking follow-up for financial analysis...",
    followup_status_earnings_done: "Financial analysis follow-up updated",
    followup_status_ai_loading: "Asking follow-up for AI advice...",
    followup_status_ai_done: "AI advice follow-up updated",
    followup_failed: "Follow-up failed: {{status}}",
    followup_failed_prefix: "Follow-up failed: {{message}}",
    export_failed: "Export failed: {{status}}",
    status_testing_finnhub: "Testing Finnhub config...",
    status_test_finnhub_done: "Finnhub test completed",
    status_testing_ai: "Testing AI config...",
    status_test_ai_done: "AI test completed",
    status_testing_exa: "Testing Exa config...",
    status_test_exa_done: "Exa test completed",
    status_testing_tavily: "Testing Tavily config...",
    status_test_tavily_done: "Tavily test completed",
    status_capturing: "Generating screenshot...",
    err_capture_lib: "Screenshot library not loaded, please refresh and retry.",
    status_capture_done: "Screenshot downloaded.",
    capture_failed: "Screenshot failed: {{message}}",
    status_watchlist_saved: "Watchlist saved.",
    status_watchlist_refreshed: "Watchlist list refreshed.",
    status_watchlist_loaded: "Watchlist loaded.",
    prompt_watchlist_rename: "Enter a new watchlist name",
    err_watchlist_name_empty: "Watchlist name cannot be empty",
    status_watchlist_renamed: "Watchlist renamed to {{name}}",
    status_watchlist_deleted: "Watchlist deleted."
  }
};

const metricsByLanguage = {
  zh: {
    realtime: [
      ["stock_name", "股票名称"],
      ["trade_date", "交易日期"],
      ["currency", "币种"],
      ["price", "股价 (本币)"],
      ["change_pct", "涨跌幅 (%)"],
      ["market_cap_b", "总市值 (十亿, 本币)"],
      ["turnover_b", "成交额 (十亿, 本币)"],
      ["pe_ttm", "PE TTM"],
      ["change_5d_pct", "5日涨跌幅 (%)"],
      ["change_20d_pct", "20日涨跌幅 (%)"],
      ["change_250d_pct", "250日涨跌幅 (%)"]
    ],
    financial: [
      ["currency", "财报币种"],
      ["latest_period", "最新财报期"],
      ["revenue_b", "营收 (十亿, 本币)"],
      ["revenue_yoy_pct", "营收 YoY (%)"],
      ["net_income_b", "利润 (十亿, 本币)"],
      ["net_income_yoy_pct", "利润 YoY (%)"],
      ["eps", "EPS (本币/股)"],
      ["gross_margin_pct", "毛利率 (%)"],
      ["net_margin_pct", "净利率 (%)"]
    ],
    prediction: [
      ["currency", "预测币种"],
      ["next_quarter_eps_forecast", "预测EPS(Next Quarter, 本币/股)"],
      ["eps_forecast", "预测EPS(Current Year, 本币/股)"],
      ["next_year_eps_forecast", "预测EPS(Next Year, 本币/股)"],
      ["next_earnings_date", "下季度财报日期"]
    ],
    forecast: [
      ["forward_pe", "Forward PE"],
      ["peg", "PEG(5yr expected)"],
      ["ev_to_ebitda", "EV/EBITDA"],
      ["ps", "P/S"],
      ["pb", "P/B"]
    ]
  },
  en: {
    realtime: [
      ["stock_name", "Stock Name"],
      ["trade_date", "Trade Date"],
      ["currency", "Currency"],
      ["price", "Price (Local)"],
      ["change_pct", "Change (%)"],
      ["market_cap_b", "Market Cap (B, Local)"],
      ["turnover_b", "Turnover (B, Local)"],
      ["pe_ttm", "PE TTM"],
      ["change_5d_pct", "5D Change (%)"],
      ["change_20d_pct", "20D Change (%)"],
      ["change_250d_pct", "250D Change (%)"]
    ],
    financial: [
      ["currency", "Financial Currency"],
      ["latest_period", "Latest Reporting Period"],
      ["revenue_b", "Revenue (B, Local)"],
      ["revenue_yoy_pct", "Revenue YoY (%)"],
      ["net_income_b", "Net Income (B, Local)"],
      ["net_income_yoy_pct", "Net Income YoY (%)"],
      ["eps", "EPS (Local/Share)"],
      ["gross_margin_pct", "Gross Margin (%)"],
      ["net_margin_pct", "Net Margin (%)"]
    ],
    prediction: [
      ["currency", "Forecast Currency"],
      ["next_quarter_eps_forecast", "EPS Forecast (Next Quarter, Local/Share)"],
      ["eps_forecast", "EPS Forecast (Current Year, Local/Share)"],
      ["next_year_eps_forecast", "EPS Forecast (Next Year, Local/Share)"],
      ["next_earnings_date", "Next Earnings Date"]
    ],
    forecast: [
      ["forward_pe", "Forward PE"],
      ["peg", "PEG (5yr expected)"],
      ["ev_to_ebitda", "EV/EBITDA"],
      ["ps", "P/S"],
      ["pb", "P/B"]
    ]
  }
};

const percentKeys = new Set([
  "change_pct",
  "change_5d_pct",
  "change_20d_pct",
  "change_250d_pct",
  "revenue_yoy_pct",
  "net_income_yoy_pct",
  "gross_margin_pct",
  "roe_pct",
  "operating_margin_pct",
  "net_margin_pct"
]);

const followupConfig = {
  earnings: {
    inputId: "earnings-followup-input",
    buttonId: "earnings-followup-btn",
    threadId: "earnings-followup-thread",
    endpoint: "/api/financial-analysis-followup",
    statusLoadingKey: "followup_status_earnings_loading",
    statusDoneKey: "followup_status_earnings_done",
    emptyTextKey: "earnings_followup_empty"
  },
  ai: {
    inputId: "ai-followup-input",
    buttonId: "ai-followup-btn",
    threadId: "ai-followup-thread",
    endpoint: "/api/ai-analysis-followup",
    statusLoadingKey: "followup_status_ai_loading",
    statusDoneKey: "followup_status_ai_done",
    emptyTextKey: "ai_followup_empty"
  }
};

const SYMBOL_TOKEN_PATTERN = /^[A-Z0-9][A-Z0-9.\-^=]{0,19}$/;

function normalizeSymbolToken(raw) {
  const symbol = String(raw || "").trim().toUpperCase();
  if (!symbol) return "";
  return SYMBOL_TOKEN_PATTERN.test(symbol) ? symbol : "";
}

function parseSymbols(raw) {
  const unique = new Set();
  const symbols = [];

  String(raw || "")
    .split(/[,\s，]+/)
    .forEach(token => {
      const symbol = normalizeSymbolToken(token);
      if (!symbol || unique.has(symbol)) return;
      unique.add(symbol);
      symbols.push(symbol);
    });

  return symbols.slice(0, 10);
}

function normalizeUiLanguage(raw) {
  const v = String(raw || "").trim().toLowerCase();
  if (v.startsWith("en")) return "en";
  return "zh";
}

function interpolate(template, vars = {}) {
  return String(template || "").replace(/\{\{(\w+)\}\}/g, (_m, key) => String(vars[key] ?? ""));
}

function t(key, vars = {}) {
  const lang = normalizeUiLanguage(state.uiLanguage);
  const dict = i18n[lang] || i18n.zh;
  const fallback = i18n.zh || {};
  const text = Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : (fallback[key] ?? key);
  return interpolate(text, vars);
}

function getMetrics() {
  return metricsByLanguage[normalizeUiLanguage(state.uiLanguage)] || metricsByLanguage.zh;
}

function applyLanguage(nextLanguage, persist = true) {
  const lang = normalizeUiLanguage(nextLanguage);
  state.uiLanguage = lang;
  if (persist) {
    localStorage.setItem(storageKeys.uiLanguage, lang);
  }

  document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  document.title = t("document_title");

  const toggleBtn = document.getElementById("language-toggle-btn");
  if (toggleBtn) {
    toggleBtn.textContent = t("lang_toggle");
  }

  for (const node of document.querySelectorAll("[data-i18n]")) {
    const key = node.getAttribute("data-i18n");
    if (!key) continue;
    node.textContent = t(key);
  }
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) {
    const key = node.getAttribute("data-i18n-placeholder");
    if (!key) continue;
    node.setAttribute("placeholder", t(key));
  }

  const openaiOption = document.querySelector('#ai-provider option[value="openai"]');
  if (openaiOption) {
    openaiOption.textContent = t("ai_provider_openai");
  }

  applyProviderDefaults(false);
  renderSymbolChips();
  renderStockErrors();
  renderWatchlistMeta();
  renderWatchlistList();
  renderFollowupThread("earnings");
  renderFollowupThread("ai");

  if (state.stocks.length) {
    renderTable("realtime-table", "realtime");
    renderTable("financial-table", "financial");
    renderTable("prediction-table", "prediction");
    renderTable("forecast-table", "forecast");
    renderExpectationPanels(state.stocks);
  } else {
    renderMarkdownOutput("beat-miss-output", "", t("beat_miss_empty"));
    renderMarkdownOutput("eps-trend-output", "", t("eps_trend_empty"));
  }
}

function syncHiddenSymbols() {
  document.getElementById("symbols").value = state.symbols.join(",");
}

function fmtTime(text) {
  if (!text) return "--";
  const d = new Date(text);
  if (Number.isNaN(d.getTime())) return String(text);
  return d.toLocaleString();
}

function getAiProvider() {
  return (document.getElementById("ai-provider").value || "gemini").toLowerCase();
}

function getConfig() {
  return {
    finnhubApiKey: document.getElementById("finnhub-api-key").value.trim(),
    aiProvider: getAiProvider(),
    aiModel: document.getElementById("ai-model").value.trim(),
    aiApiKey: document.getElementById("ai-api-key").value.trim(),
    aiBaseUrl: document.getElementById("ai-base-url").value.trim(),
    exaApiKey: document.getElementById("exa-api-key").value.trim(),
    tavilyApiKey: document.getElementById("tavily-api-key").value.trim()
  };
}

function saveConfig() {
  const cfg = getConfig();
  localStorage.setItem(storageKeys.finnhubApiKey, cfg.finnhubApiKey);
  localStorage.setItem(storageKeys.aiProvider, cfg.aiProvider);
  localStorage.setItem(storageKeys.aiModel, cfg.aiModel);
  localStorage.setItem(storageKeys.aiApiKey, cfg.aiApiKey);
  localStorage.setItem(storageKeys.aiBaseUrl, cfg.aiBaseUrl);
  localStorage.setItem(storageKeys.exaApiKey, cfg.exaApiKey);
  localStorage.setItem(storageKeys.tavilyApiKey, cfg.tavilyApiKey);
}

function loadConfig() {
  document.getElementById("finnhub-api-key").value = localStorage.getItem(storageKeys.finnhubApiKey) || "";

  const provider = (localStorage.getItem(storageKeys.aiProvider) || "openai").toLowerCase();
  document.getElementById("ai-provider").value = ["openai", "gemini", "claude"].includes(provider)
    ? provider
    : "openai";

  document.getElementById("ai-model").value = localStorage.getItem(storageKeys.aiModel) || "";
  document.getElementById("ai-api-key").value = localStorage.getItem(storageKeys.aiApiKey) || "";
  document.getElementById("ai-base-url").value = localStorage.getItem(storageKeys.aiBaseUrl) || "";
  document.getElementById("exa-api-key").value = localStorage.getItem(storageKeys.exaApiKey) || "";
  document.getElementById("tavily-api-key").value = localStorage.getItem(storageKeys.tavilyApiKey) || "";
  const pageDefaultLanguage = normalizeUiLanguage(document.getElementById("default-ui-language")?.value || "zh");
  const language = normalizeUiLanguage(localStorage.getItem(storageKeys.uiLanguage) || pageDefaultLanguage);
  applyLanguage(language, false);
}

function applyProviderDefaults(forceModel = true) {
  const provider = getAiProvider();
  const modelInput = document.getElementById("ai-model");
  const baseUrlInput = document.getElementById("ai-base-url");

  if (forceModel && !modelInput.value.trim()) {
    modelInput.value = defaultModels[provider] || "";
  }

  if (provider === "openai") {
    baseUrlInput.disabled = false;
    baseUrlInput.placeholder = t("ai_base_url_placeholder");
  } else {
    baseUrlInput.disabled = true;
    baseUrlInput.placeholder = t("ai_base_url_placeholder_non_openai");
  }
}

function renderSymbolChips() {
  const wrap = document.getElementById("symbol-chips");
  if (!state.symbols.length) {
    wrap.innerHTML = `<span class="chip-empty">${t("chip_empty")}</span>`;
    syncHiddenSymbols();
    return;
  }

  let html = "";
  state.symbols.forEach(symbol => {
    html += `<span class="chip">${symbol}<button type="button" class="chip-del" data-symbol="${symbol}" title="${t("remove")}">×</button></span>`;
  });
  wrap.innerHTML = html;
  syncHiddenSymbols();
}

function addSymbol(symbolRaw) {
  const symbol = normalizeSymbolToken(symbolRaw);
  if (!symbol) return;
  if (state.symbols.includes(symbol)) return;
  if (state.symbols.length >= 10) return;
  state.symbols.push(symbol);
  renderSymbolChips();
}

function removeSymbol(symbol) {
  state.symbols = state.symbols.filter(s => s !== symbol);
  renderSymbolChips();
}

function renderWatchlistMeta() {
  const el = document.getElementById("watchlist-meta");
  if (!el) return;

  const count = state.watchlist.items.length;
  if (!count) {
    el.textContent = t("watchlist_empty");
    return;
  }
  const latest = state.watchlist.items[0]?.updated_at;
  el.textContent = t("watchlist_saved_meta", { count, time: fmtTime(latest) });
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeCompareErrors(items) {
  const out = [];
  const seen = new Set();
  (Array.isArray(items) ? items : []).forEach((item) => {
    const symbol = String(item?.symbol || "").trim().toUpperCase() || "--";
    const message = String(item?.error || item?.message || "").trim();
    if (!message) return;
    const key = `${symbol}::${message}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ symbol, error: message });
  });
  return out;
}

function isMissingDisplayValue(value) {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim() === "";
  if (typeof value === "number") return Number.isNaN(value);
  return false;
}

function stockDisplayValue(stock, sectionKey, key) {
  if (key === "currency") {
    const ccy = getSectionCurrency(stock, sectionKey);
    return ccy === "--" ? null : ccy;
  }
  return stock?.[sectionKey]?.[key];
}

function stockHasMissingDisplayData(stock) {
  const metrics = getMetrics();
  const sectionKeys = ["realtime", "financial", "prediction", "forecast"];
  for (const sectionKey of sectionKeys) {
    const rows = Array.isArray(metrics?.[sectionKey]) ? metrics[sectionKey] : [];
    for (const row of rows) {
      const key = Array.isArray(row) ? row[0] : null;
      if (!key) continue;
      if (isMissingDisplayValue(stockDisplayValue(stock, sectionKey, key))) {
        return true;
      }
    }
  }
  return false;
}

function buildMissingDataSymbolSet(stocks) {
  const set = new Set();
  (Array.isArray(stocks) ? stocks : []).forEach((stock) => {
    const symbol = String(stock?.symbol || "").trim().toUpperCase();
    if (!symbol) return;
    if (stockHasMissingDisplayData(stock)) {
      set.add(symbol);
    }
  });
  return set;
}

function collectCompareErrors(data, stocks) {
  const merged = [];
  const hasStockRows = Array.isArray(stocks) && stocks.length > 0;
  const missingDataSymbols = buildMissingDataSymbolSet(stocks);
  const shouldShowWarning = (symbol) => {
    if (!hasStockRows) return true;
    return missingDataSymbols.has(symbol);
  };

  if (Array.isArray(data?.errors)) merged.push(...data.errors);
  if (Array.isArray(data?.details?.errors)) merged.push(...data.details.errors);
  if (Array.isArray(data?.warnings)) {
    data.warnings.forEach((item) => {
      const symbol = String(item?.symbol || "").trim().toUpperCase();
      if (!shouldShowWarning(symbol)) return;
      merged.push(item);
    });
  }
  (Array.isArray(stocks) ? stocks : []).forEach((stock) => {
    const symbol = String(stock?.symbol || "").trim().toUpperCase() || "--";
    const hasMissingData = missingDataSymbols.has(symbol);
    const message = String(stock?.error || "").trim();
    if (message) {
      merged.push({
        symbol,
        error: message
      });
    }
    const warningItems = Array.isArray(stock?.warnings) ? stock.warnings : [];
    if (!hasMissingData) return;
    warningItems.forEach((warning) => {
      if (!warning || typeof warning !== "object") return;
      const source = String(warning.source || "").trim();
      const statusCode = warning.status_code;
      const base = String(warning.message || warning.error || "").trim();
      if (!base) return;
      let text = base;
      if (source) text = `[${source}] ${text}`;
      if (statusCode !== undefined && statusCode !== null && !text.includes(`HTTP ${statusCode}`)) {
        text = `${text} (HTTP ${statusCode})`;
      }
      merged.push({
        symbol,
        error: text
      });
    });
  });
  return normalizeCompareErrors(merged);
}

function dismissCompareErrors() {
  state.compareErrorsDismissed = true;
  renderStockErrors();
}

function renderStockErrors() {
  const panel = document.getElementById("compare-error-panel");
  const title = document.getElementById("compare-error-title");
  const list = document.getElementById("compare-error-list");
  const dismissBtn = document.getElementById("compare-error-dismiss-btn");
  if (!panel || !title || !list) return;

  const errors = Array.isArray(state.stockErrors) ? state.stockErrors : [];
  if (dismissBtn) {
    dismissBtn.textContent = t("compare_error_dismiss_btn");
  }
  if (!errors.length) {
    panel.hidden = true;
    list.innerHTML = "";
    return;
  }
  if (state.compareErrorsDismissed) {
    panel.hidden = true;
    list.innerHTML = "";
    return;
  }

  title.textContent = t("compare_error_panel_title", { count: errors.length });
  list.innerHTML = errors
    .map((item) => `<li><strong>${escapeHtml(item.symbol)}</strong>: ${escapeHtml(item.error)}</li>`)
    .join("");
  panel.hidden = false;
}

function renderWatchlistList() {
  const wrap = document.getElementById("watchlist-list");
  if (!wrap) return;
  if (!state.watchlist.items.length) {
    wrap.innerHTML = `<div class="watchlist-empty">${t("watchlist_empty")}</div>`;
    return;
  }

  let html = "";
  state.watchlist.items.forEach(item => {
    const symbols = Array.isArray(item.symbols) ? item.symbols.join(", ") : "";
    html += `
      <div class="watchlist-item" data-id="${item.id}">
        <div class="watchlist-title">${escapeHtml(item.name || t("watchlist_unknown_name"))} | ${fmtTime(item.updated_at)}</div>
        <div class="watchlist-actions">
          <button type="button" class="watchlist-load-btn" data-id="${item.id}">${t("watchlist_load_btn")}</button>
          <button type="button" class="watchlist-rename-btn" data-id="${item.id}">${t("watchlist_rename_btn")}</button>
          <button type="button" class="watchlist-delete-btn" data-id="${item.id}">${t("watchlist_delete_btn")}</button>
        </div>
        <div class="watchlist-symbols">${escapeHtml(symbols || "--")}</div>
      </div>
    `;
  });
  wrap.innerHTML = html;
}

async function loadWatchlists() {
  const resp = await fetch("/api/watchlist");
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || t("err_load_watchlist", { status: resp.status }));
  }
  state.watchlist.items = Array.isArray(data.items) ? data.items : [];
  state.watchlist.refreshedAt = new Date().toISOString();
  renderWatchlistMeta();
  renderWatchlistList();
}

async function saveWatchlist() {
  if (!state.symbols.length) {
    throw new Error(t("err_need_watchlist_symbol"));
  }
  const nameInput = document.getElementById("watchlist-name");
  const name = (nameInput?.value || "").trim();

  const resp = await fetch("/api/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, symbols: state.symbols })
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || t("err_save_watchlist", { status: resp.status }));
  }

  if (nameInput) nameInput.value = "";
  await loadWatchlists();
}

async function loadWatchlistById(recordId) {
  const resp = await fetch(`/api/watchlist/${encodeURIComponent(recordId)}`);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || t("err_load_watchlist", { status: resp.status }));
  }
  const symbols = Array.isArray(data.symbols) ? parseSymbols(data.symbols.join(",")) : [];
  if (!symbols.length) {
    throw new Error(t("err_empty_watchlist"));
  }
  state.symbols = symbols;
  renderSymbolChips();
}

async function deleteWatchlistById(recordId) {
  const resp = await fetch(`/api/watchlist/${encodeURIComponent(recordId)}`, {
    method: "DELETE"
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || t("err_delete_watchlist", { status: resp.status }));
  }
  if (!data.ok) {
    throw new Error(t("err_watchlist_not_found"));
  }
  await loadWatchlists();
}

async function renameWatchlistById(recordId, name) {
  const resp = await fetch(`/api/watchlist/${encodeURIComponent(recordId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || t("err_rename_watchlist", { status: resp.status }));
  }
  await loadWatchlists();
  return data;
}

function inlineMarkdown(text) {
  let s = escapeHtml(text);
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/`(.+?)`/g, "<code>$1</code>");
  s = s.replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return s;
}

function basicMarkdownToHtml(mdText) {
  const lines = String(mdText || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let inUl = false;
  let inOl = false;
  let inCode = false;
  let codeLines = [];

  const closeLists = () => {
    if (inUl) {
      html.push("</ul>");
      inUl = false;
    }
    if (inOl) {
      html.push("</ol>");
      inOl = false;
    }
  };

  const flushCode = () => {
    if (!inCode) return;
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    inCode = false;
    codeLines = [];
  };

  for (const rawLine of lines) {
    const line = rawLine ?? "";
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      closeLists();
      if (inCode) {
        flushCode();
      } else {
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (!trimmed) {
      closeLists();
      continue;
    }

    const h = /^(#{1,6})\s+(.+)$/.exec(trimmed);
    if (h) {
      closeLists();
      const level = h[1].length;
      html.push(`<h${level}>${inlineMarkdown(h[2])}</h${level}>`);
      continue;
    }

    const ul = /^[-*]\s+(.+)$/.exec(trimmed);
    if (ul) {
      if (inOl) {
        html.push("</ol>");
        inOl = false;
      }
      if (!inUl) {
        html.push("<ul>");
        inUl = true;
      }
      html.push(`<li>${inlineMarkdown(ul[1])}</li>`);
      continue;
    }

    const ol = /^\d+\.\s+(.+)$/.exec(trimmed);
    if (ol) {
      if (inUl) {
        html.push("</ul>");
        inUl = false;
      }
      if (!inOl) {
        html.push("<ol>");
        inOl = true;
      }
      html.push(`<li>${inlineMarkdown(ol[1])}</li>`);
      continue;
    }

    closeLists();
    html.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  }

  flushCode();
  closeLists();
  return html.join("\n");
}

function renderMarkdownOutput(elementId, markdownText, emptyText = t("markdown_empty")) {
  const output = document.getElementById(elementId);
  const text = String(markdownText || "").trim();
  if (!text) {
    output.textContent = emptyText;
    return;
  }

  const disableLinks = () => {
    for (const a of output.querySelectorAll("a")) {
      const href = a.getAttribute("href");
      const label = (a.textContent || "").trim();
      const replacement = document.createElement("span");
      replacement.textContent = href ? `${label} (${href})` : label;
      a.replaceWith(replacement);
    }
  };

  if (window.marked && window.DOMPurify) {
    const html = window.marked.parse(text, { breaks: true, gfm: true });
    output.innerHTML = window.DOMPurify.sanitize(html);
    disableLinks();
    return;
  }
  output.innerHTML = basicMarkdownToHtml(text);
  disableLinks();
}

function markdownToSafeHtml(markdownText) {
  const text = String(markdownText || "").trim();
  if (!text) return "";
  if (window.marked && window.DOMPurify) {
    return window.DOMPurify.sanitize(window.marked.parse(text, { breaks: true, gfm: true }));
  }
  return basicMarkdownToHtml(text);
}

function disableLinksInNode(node) {
  if (!node) return;
  for (const a of node.querySelectorAll("a")) {
    const href = a.getAttribute("href");
    const label = (a.textContent || "").trim();
    const replacement = document.createElement("span");
    replacement.textContent = href ? `${label} (${href})` : label;
    a.replaceWith(replacement);
  }
}

function setFollowupControls(type, enabled) {
  const cfg = followupConfig[type];
  if (!cfg) return;

  const loading = Boolean(state.followupLoading[type]);
  const input = document.getElementById(cfg.inputId);
  const button = document.getElementById(cfg.buttonId);
  if (input) input.disabled = !enabled || loading;
  if (button) button.disabled = !enabled || loading;
}

function renderFollowupThread(type) {
  const cfg = followupConfig[type];
  if (!cfg) return;

  const wrap = document.getElementById(cfg.threadId);
  if (!wrap) return;

  const messages = Array.isArray(state.followups[type]) ? state.followups[type] : [];
  if (!messages.length) {
    wrap.innerHTML = `<div class="followup-empty">${t(cfg.emptyTextKey)}</div>`;
    return;
  }

  let html = "";
  messages.forEach(msg => {
    const role = msg.role === "assistant" ? "assistant" : "user";
    const roleLabel = role === "assistant" ? "AI" : t("followup_you");
    const bubble = role === "assistant"
      ? markdownToSafeHtml(msg.content)
      : `<p>${escapeHtml(msg.content)}</p>`;
    html += `
      <div class="followup-item ${role}">
        <div class="followup-role">${roleLabel}</div>
        <div class="followup-bubble">${bubble}</div>
      </div>
    `;
  });

  wrap.innerHTML = html;
  disableLinksInNode(wrap);
  wrap.scrollTop = wrap.scrollHeight;
}

function resetFollowup(type) {
  const cfg = followupConfig[type];
  if (!cfg) return;

  state.followups[type] = [];
  state.followupLoading[type] = false;

  const input = document.getElementById(cfg.inputId);
  if (input) input.value = "";

  renderFollowupThread(type);
  setFollowupControls(type, false);
}

function setFollowupReady(type, ready) {
  state.followupLoading[type] = false;
  setFollowupControls(type, Boolean(ready));
  renderFollowupThread(type);
}

function stripReferenceSection(markdownText) {
  const raw = String(markdownText || "");
  const lines = raw.split(/\r?\n/);
  const headerIndex = lines.findIndex((line) => {
    const normalized = String(line || "")
      .replace(/[*_`#>\-\s]/g, "")
      .replace(/^\d+[.)、:：]*/, "")
      .replace(/[：:].*$/, "");
    return normalized.startsWith("参考来源") || normalized.toLowerCase().startsWith("references");
  });
  if (headerIndex < 0) return raw.trim();
  return lines.slice(0, headerIndex).join("\n").trim();
}

function renderAiOutput(markdownText) {
  const cleaned = stripReferenceSection(markdownText);
  state.analysis.ai = cleaned;
  renderMarkdownOutput("ai-output", cleaned, t("markdown_empty"));
}

function renderTargetPriceOutput(markdownText, emptyText = t("target_initial_empty")) {
  const cleaned = stripReferenceSection(markdownText);
  state.analysis.targetPrice = cleaned;
  renderMarkdownOutput("target-price-output", cleaned, emptyText);
}

function renderEarningsOutput(markdownText, emptyText = t("earnings_initial_empty")) {
  const cleaned = stripReferenceSection(markdownText);
  state.analysis.earnings = cleaned;
  renderMarkdownOutput("earnings-output", cleaned, emptyText);
}

async function writeClipboardText(text) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (_err) {
      // fallback below
    }
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "readonly");
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(area);
  if (!ok) {
    throw new Error(t("err_copy_manual"));
  }
}

async function copyAnalysisOutput(type) {
  const mapping = {
    targetPrice: { label: t("target_label"), text: state.analysis.targetPrice },
    earnings: { label: t("earnings_label"), text: state.analysis.earnings },
    ai: { label: t("ai_label"), text: state.analysis.ai }
  };
  const target = mapping[type];
  if (!target) return;

  const text = String(target.text || "").trim();
  if (!text) {
    throw new Error(t("err_copy_no_content", { label: target.label }));
  }
  await writeClipboardText(text);
  document.getElementById("status").textContent = t("status_copied", { label: target.label });
}

function fmt(value, key) {
  if (value === null || value === undefined) return "--";
  if (key === "latest_period_type") {
    if (String(value).toLowerCase() === "quarterly") return t("latest_period_quarterly");
    if (String(value).toLowerCase() === "annual") return t("latest_period_annual");
  }
  if (typeof value === "string") return value || "--";
  if (Number.isNaN(Number(value))) return "--";
  if (percentKeys.has(key) || key.endsWith("_pct")) return `${Number(value).toFixed(2)}%`;
  return Number(value).toFixed(2);
}

function fmtNumberMaybe(value, digits = 2) {
  if (value === null || value === undefined) return "--";
  const num = Number(value);
  if (Number.isNaN(num)) return "--";
  return num.toFixed(digits);
}

function fmtPercentMaybe(value, digits = 2) {
  if (value === null || value === undefined) return "--";
  const num = Number(value);
  if (Number.isNaN(num)) return "--";
  return `${num.toFixed(digits)}%`;
}

function buildBeatMissMarkdown(stocks) {
  if (!Array.isArray(stocks) || stocks.length === 0) {
    return t("err_need_fetch_data");
  }

  const sections = [];
  stocks.forEach((stock) => {
    const symbol = String(stock?.symbol || "--").toUpperCase();
    const block = stock?.expectation_guidance || {};
    const beatMiss = block?.beat_miss || {};
    const conclusion = block?.conclusion || {};

    const surprises = Array.isArray(beatMiss.history_surprise_pct_4q)
      ? beatMiss.history_surprise_pct_4q
          .filter((v) => v !== null && v !== undefined && !Number.isNaN(Number(v)))
          .map((v) => fmtPercentMaybe(v))
          .join(" / ")
      : "";

    sections.push(
      [
        `### ${symbol}`,
        t("beat_miss_panel_title"),
        t("beat_miss_line_latest", {
          latest_quarter: beatMiss.latest_quarter || "--",
          eps_actual: fmtNumberMaybe(beatMiss.latest_eps_actual),
          eps_estimate: fmtNumberMaybe(beatMiss.latest_eps_estimate),
          surprise: fmtPercentMaybe(beatMiss.latest_surprise_pct),
          result: beatMiss.latest_result || "--"
        }),
        t("beat_miss_line_recent", {
          surprises: surprises || "--",
          beat: beatMiss.beat_count_4q ?? "--",
          miss: beatMiss.miss_count_4q ?? "--",
          streak: beatMiss.beat_streak_4q ?? "--"
        }),
        t("beat_miss_line_conclusion", {
          conclusion: conclusion.beat_miss || beatMiss.conclusion || t("info_insufficient")
        })
      ].join("\n")
    );
  });

  return sections.join("\n\n");
}

function buildEpsTrendMarkdown(stocks) {
  if (!Array.isArray(stocks) || stocks.length === 0) {
    return t("err_need_fetch_data");
  }

  const sections = [];
  stocks.forEach((stock) => {
    const symbol = String(stock?.symbol || "--").toUpperCase();
    const block = stock?.expectation_guidance || {};
    const epsTrend = block?.eps_trend || {};
    const conclusion = block?.conclusion || {};

    sections.push(
      [
        `### ${symbol}`,
        t("eps_trend_panel_title"),
        t("eps_trend_line_basis", {
          period: epsTrend.period || "--",
          current: fmtNumberMaybe(epsTrend.current),
          d7: fmtNumberMaybe(epsTrend.d7),
          d30: fmtNumberMaybe(epsTrend.d30),
          d60: fmtNumberMaybe(epsTrend.d60),
          d90: fmtNumberMaybe(epsTrend.d90)
        }),
        t("eps_trend_line_change", {
          vs30: fmtPercentMaybe(epsTrend.change_vs_30d_pct),
          vs90: fmtPercentMaybe(epsTrend.change_vs_90d_pct),
          signal: epsTrend.signal || "--"
        }),
        t("eps_trend_line_conclusion", {
          conclusion: conclusion.eps_trend || epsTrend.conclusion || t("info_insufficient")
        })
      ].join("\n")
    );
  });

  return sections.join("\n\n");
}

function renderExpectationPanels(stocks) {
  renderMarkdownOutput("beat-miss-output", buildBeatMissMarkdown(stocks), t("beat_miss_no_data"));
  renderMarkdownOutput("eps-trend-output", buildEpsTrendMarkdown(stocks), t("eps_trend_no_data"));
}

function getSectionCurrency(stock, sectionKey) {
  const currency = stock?.currency || {};
  if (sectionKey === "realtime") {
    return stock?.realtime?.currency || currency.quote || currency.financial || currency.forecast || "--";
  }
  if (sectionKey === "financial") {
    return stock?.financial?.currency || currency.financial || currency.quote || currency.forecast || "--";
  }
  if (sectionKey === "prediction") {
    return stock?.forecast?.currency || currency.forecast || currency.financial || currency.quote || "--";
  }
  return "--";
}

function renderTable(tableId, sectionKey) {
  const table = document.getElementById(tableId);
  const metrics = getMetrics();
  const cols = state.stocks.map(stock => {
    const symbol = stock?.symbol || "--";
    const ccy = getSectionCurrency(stock, sectionKey);
    return ccy && ccy !== "--" ? `${symbol} (${ccy})` : symbol;
  });

  let html = `<thead><tr><th>${t("table_metric")}</th>`;
  cols.forEach(s => {
    html += `<th>${s}</th>`;
  });
  html += "</tr></thead><tbody>";

  metrics[sectionKey].forEach(([key, label]) => {
    html += `<tr><td>${label}</td>`;
    state.stocks.forEach(stock => {
      const v = key === "currency" ? getSectionCurrency(stock, sectionKey) : stock[sectionKey]?.[key];
      html += `<td>${fmt(v, key)}</td>`;
    });
    html += "</tr>";
  });

  html += "</tbody>";
  table.innerHTML = html;
}

async function fetchCompare(forceRefreshFinancial = false) {
  const status = document.getElementById("status");
  if (!state.symbols.length) {
    status.textContent = t("err_need_symbol");
    return;
  }

  const cfg = getConfig();
  state.compareErrorsDismissed = false;
  state.stockErrors = [];
  renderStockErrors();

  status.textContent = forceRefreshFinancial ? t("status_fetching_force") : t("status_fetching");
  const symbolsQuery = state.symbols.join(",");
  const headers = {};
  if (cfg.finnhubApiKey) headers["X-Finnhub-Api-Key"] = cfg.finnhubApiKey;
  const resp = await fetch(
    `/api/compare?symbols=${encodeURIComponent(symbolsQuery)}&force_financial_refresh=${forceRefreshFinancial ? "1" : "0"}&_ts=${Date.now()}`,
    {
      cache: "no-store",
      headers
    }
  );

  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    state.compareErrorsDismissed = false;
    state.stockErrors = collectCompareErrors(data, data?.stocks);
    renderStockErrors();
    throw new Error(data.error || data.message || t("err_api_failed", { status: resp.status }));
  }

  const data = await resp.json();
  state.symbols = data.symbols || state.symbols;
  state.stocks = (Array.isArray(data.stocks) ? data.stocks : []).map((stock) => ({
    ...(stock || {}),
    financial: (() => {
      const financial = (stock && stock.financial && typeof stock.financial === "object")
        ? { ...stock.financial }
        : {};
      if (!financial.latest_report_date) {
        financial.latest_report_date = financial.latest_period || null;
      }
      return financial;
    })(),
    prediction: (stock && stock.forecast && typeof stock.forecast === "object") ? stock.forecast : {}
  }));
  state.compareErrorsDismissed = false;
  state.stockErrors = collectCompareErrors(data, state.stocks);
  renderStockErrors();
  renderSymbolChips();

  renderTable("realtime-table", "realtime");
  renderTable("financial-table", "financial");
  renderTable("prediction-table", "prediction");
  renderTable("forecast-table", "forecast");
  renderExpectationPanels(state.stocks);
  renderTargetPriceOutput(t("prompt_generate_target"));
  renderEarningsOutput("", t("prompt_generate_earnings"));
  renderAiOutput(t("prompt_generate_ai"));
  resetFollowup("earnings");
  resetFollowup("ai");

  document.getElementById("target-price-btn").disabled = state.stocks.length === 0;
  document.getElementById("earnings-btn").disabled = state.stocks.length === 0;
  document.getElementById("ai-btn").disabled = state.stocks.length === 0;
  status.textContent = t("status_data_time", { time: fmtTime(data.generated_at) });
  if (state.stockErrors.length) {
    status.textContent = `${status.textContent} | ${t("compare_partial_failed", { count: state.stockErrors.length })}`;
  }
}

async function generateTargetPriceAnalysis() {
  const status = document.getElementById("status");
  const cfg = getConfig();

  if (!state.stocks.length) {
    renderTargetPriceOutput(t("err_need_fetch_data"));
    return;
  }
  if (!cfg.aiApiKey || !cfg.aiModel) {
    renderTargetPriceOutput(t("err_need_ai_config"));
    return;
  }

  renderTargetPriceOutput(t("target_generating"));
  status.textContent = t("status_target_generating");

  const resp = await fetch("/api/target-price-analysis", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbols: state.symbols,
      stocks: state.stocks,
      provider: cfg.aiProvider,
      api_key: cfg.aiApiKey,
      model: cfg.aiModel,
      base_url: cfg.aiBaseUrl,
      exa_api_key: cfg.exaApiKey,
      tavily_api_key: cfg.tavilyApiKey,
      finnhub_api_key: cfg.finnhubApiKey,
      language: state.uiLanguage
    })
  });

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    renderTargetPriceOutput(errData.error || t("action_failed", { status: resp.status }));
    return;
  }

  const data = await resp.json();
  renderTargetPriceOutput(data.analysis || t("markdown_empty"));
  status.textContent = data.provider && data.model
    ? t("status_target_done_with_model", { provider: data.provider, model: data.model })
    : t("status_target_done");
}

async function generateFinancialAnalysis() {
  const status = document.getElementById("status");
  const cfg = getConfig();
  const hasAiConfig = Boolean(cfg.aiApiKey && cfg.aiModel);

  if (!state.stocks.length) {
    renderEarningsOutput(t("err_need_fetch_data"));
    setFollowupReady("earnings", false);
    return;
  }

  resetFollowup("earnings");
  renderEarningsOutput(t("earnings_generating"));
  status.textContent = hasAiConfig ? t("status_earnings_generating_ai") : t("status_earnings_generating");

  const resp = await fetch("/api/financial-analysis", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbols: state.symbols,
      stocks: state.stocks,
      finnhub_api_key: cfg.finnhubApiKey,
      provider: cfg.aiProvider,
      api_key: cfg.aiApiKey,
      model: cfg.aiModel,
      base_url: cfg.aiBaseUrl,
      exa_api_key: cfg.exaApiKey,
      tavily_api_key: cfg.tavilyApiKey,
      language: state.uiLanguage
    })
  });

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    renderEarningsOutput(errData.error || t("action_failed", { status: resp.status }));
    setFollowupReady("earnings", false);
    return;
  }

  const data = await resp.json();
  renderEarningsOutput(data.analysis || t("markdown_empty"));
  setFollowupReady("earnings", Boolean(String(data.analysis || "").trim()));
  status.textContent = data.provider && data.model
    ? t("status_earnings_done_with_model", { provider: data.provider, model: data.model })
    : t("status_earnings_done");
}

async function generateAi() {
  const status = document.getElementById("status");
  const cfg = getConfig();

  if (!cfg.aiApiKey || !cfg.aiModel) {
    renderAiOutput(t("err_need_ai_config"));
    setFollowupReady("ai", false);
    return;
  }

  resetFollowup("ai");
  renderAiOutput(t("ai_generating"));
  status.textContent = t("status_ai_generating");

  const resp = await fetch("/api/ai-analysis", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbols: state.symbols,
      stocks: state.stocks,
      provider: cfg.aiProvider,
      api_key: cfg.aiApiKey,
      model: cfg.aiModel,
      base_url: cfg.aiBaseUrl,
      exa_api_key: cfg.exaApiKey,
      tavily_api_key: cfg.tavilyApiKey,
      finnhub_api_key: cfg.finnhubApiKey,
      language: state.uiLanguage
    })
  });

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    renderAiOutput(errData.error || t("err_api_failed", { status: resp.status }));
    setFollowupReady("ai", false);
    return;
  }

  const data = await resp.json();
  renderAiOutput(data.analysis || t("markdown_empty"));
  setFollowupReady("ai", Boolean(String(data.analysis || "").trim()));
  status.textContent = t("ai_model_status", { provider: data.provider || "--", model: data.model || "--" });
}

async function submitFollowup(type) {
  const cfg = followupConfig[type];
  if (!cfg) return;

  const status = document.getElementById("status");
  const input = document.getElementById(cfg.inputId);
  const question = (input?.value || "").trim();
  if (!question) {
    throw new Error(t("err_followup_empty"));
  }

  const baseAnalysis = String(type === "earnings" ? state.analysis.earnings : state.analysis.ai).trim();
  if (!baseAnalysis) {
    throw new Error(t("err_followup_need_base"));
  }

  const aiCfg = getConfig();
  if (!aiCfg.aiApiKey || !aiCfg.aiModel) {
    throw new Error(t("err_need_ai_config"));
  }

  const history = (Array.isArray(state.followups[type]) ? state.followups[type] : [])
    .map((msg) => ({
      role: msg.role === "assistant" ? "assistant" : "user",
      content: String(msg.content || "").trim()
    }))
    .filter((msg) => msg.content);

  state.followups[type].push({ role: "user", content: question });
  renderFollowupThread(type);
  if (input) input.value = "";

  state.followupLoading[type] = true;
  setFollowupControls(type, true);
  status.textContent = t(cfg.statusLoadingKey);

  try {
    const resp = await fetch(cfg.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbols: state.symbols,
        stocks: state.stocks,
        finnhub_api_key: aiCfg.finnhubApiKey,
        provider: aiCfg.aiProvider,
        api_key: aiCfg.aiApiKey,
        model: aiCfg.aiModel,
        base_url: aiCfg.aiBaseUrl,
        exa_api_key: aiCfg.exaApiKey,
        tavily_api_key: aiCfg.tavilyApiKey,
        base_analysis: baseAnalysis,
        history,
        question,
        language: state.uiLanguage
      })
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.error || t("followup_failed", { status: resp.status }));
    }

    const answer = String(data.answer || t("markdown_empty")).trim() || t("markdown_empty");
    state.followups[type].push({ role: "assistant", content: answer });
    status.textContent = t(cfg.statusDoneKey);
  } catch (err) {
    state.followups[type].push({ role: "assistant", content: t("followup_failed_prefix", { message: err.message }) });
    status.textContent = err.message;
  } finally {
    state.followupLoading[type] = false;
    setFollowupControls(type, true);
    renderFollowupThread(type);
  }
}

async function exportExcel() {
  if (!state.symbols.length) return;
  const cfg = getConfig();

  const resp = await fetch("/api/export-excel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols: state.symbols, finnhub_api_key: cfg.finnhubApiKey })
  });

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    throw new Error(errData.error || t("export_failed", { status: resp.status }));
  }

  const blob = await resp.blob();
  const cd = resp.headers.get("content-disposition") || "";
  const match = /filename=([^;]+)/i.exec(cd);
  const filename = match ? decodeURIComponent(match[1].replaceAll('"', "")) : "stockanalysiskit.xlsx";

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function testFinnhubConfig() {
  const status = document.getElementById("status");
  const cfg = getConfig();
  status.textContent = t("status_testing_finnhub");

  const resp = await fetch("/api/test-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target: "finnhub", finnhub_api_key: cfg.finnhubApiKey })
  });
  const data = await resp.json().catch(() => ({}));
  status.textContent = data.message || (resp.ok ? t("status_test_finnhub_done") : t("err_api_failed", { status: resp.status }));
}

async function testAiConfig() {
  const status = document.getElementById("status");
  const cfg = getConfig();
  status.textContent = t("status_testing_ai");

  const resp = await fetch("/api/test-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: "ai",
      provider: cfg.aiProvider,
      api_key: cfg.aiApiKey,
      model: cfg.aiModel,
      base_url: cfg.aiBaseUrl
    })
  });
  const data = await resp.json().catch(() => ({}));
  status.textContent = data.message || (resp.ok ? t("status_test_ai_done") : t("err_api_failed", { status: resp.status }));
}

async function testExaConfig() {
  const status = document.getElementById("status");
  const cfg = getConfig();
  status.textContent = t("status_testing_exa");

  const resp = await fetch("/api/test-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: "exa",
      exa_api_key: cfg.exaApiKey
    })
  });
  const data = await resp.json().catch(() => ({}));
  status.textContent = data.message || (resp.ok ? t("status_test_exa_done") : t("err_api_failed", { status: resp.status }));
}

async function testTavilyConfig() {
  const status = document.getElementById("status");
  const cfg = getConfig();
  status.textContent = t("status_testing_tavily");

  const resp = await fetch("/api/test-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: "tavily",
      tavily_api_key: cfg.tavilyApiKey
    })
  });
  const data = await resp.json().catch(() => ({}));
  status.textContent = data.message || (resp.ok ? t("status_test_tavily_done") : t("err_api_failed", { status: resp.status }));
}

async function captureScreen() {
  const status = document.getElementById("status");
  const target = document.getElementById("capture-target");
  status.textContent = t("status_capturing");

  if (typeof window.html2canvas !== "function") {
    throw new Error(t("err_capture_lib"));
  }

  const canvas = await window.html2canvas(target, {
    scale: Math.max(2, window.devicePixelRatio || 1),
    backgroundColor: "#eef3fb",
    useCORS: true,
    logging: false,
    scrollY: -window.scrollY,
    onclone: (clonedDoc) => {
      const style = clonedDoc.createElement("style");
      style.textContent = `
        * { animation: none !important; transition: none !important; }
        .toolbar, .hero, main > section, .watchlist-panel, .watchlist-list, .followup-panel, .followup-thread, #status {
          backdrop-filter: none !important;
          -webkit-backdrop-filter: none !important;
        }
        .toolbar, .hero, main > section, .watchlist-panel, .watchlist-list, .followup-panel, .followup-thread {
          background: #ffffff !important;
        }
      `;
      clonedDoc.head.appendChild(style);

      const clonedStatus = clonedDoc.getElementById("status");
      if (clonedStatus) {
        clonedStatus.style.display = "none";
      }
    }
  });

  const a = document.createElement("a");
  const symbols = state.symbols.length ? state.symbols.join("_") : "stocks";
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  a.href = canvas.toDataURL("image/png");
  a.download = `stockanalysiskit_${symbols}_${ts}.png`;
  a.click();
  status.textContent = t("status_capture_done");
}

function bindEvents() {
  const dismissCompareErrorBtn = document.getElementById("compare-error-dismiss-btn");
  if (dismissCompareErrorBtn) {
    dismissCompareErrorBtn.addEventListener("click", dismissCompareErrors);
  }

  document.getElementById("language-toggle-btn").addEventListener("click", () => {
    const next = state.uiLanguage === "en" ? "zh" : "en";
    applyLanguage(next, true);
  });

  document.getElementById("add-symbol-btn").addEventListener("click", () => {
    const input = document.getElementById("new-symbol");
    addSymbol(input.value);
    input.value = "";
  });

  document.getElementById("new-symbol").addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      document.getElementById("add-symbol-btn").click();
    }
  });

  document.getElementById("symbol-chips").addEventListener("click", e => {
    const btn = e.target.closest(".chip-del");
    if (!btn) return;
    removeSymbol(btn.dataset.symbol);
  });

  ["finnhub-api-key", "ai-model", "ai-api-key", "ai-base-url", "exa-api-key", "tavily-api-key"].forEach(id => {
    document.getElementById(id).addEventListener("input", saveConfig);
  });

  document.getElementById("ai-provider").addEventListener("change", () => {
    applyProviderDefaults(true);
    saveConfig();
  });

  document.getElementById("test-finnhub-btn").addEventListener("click", async () => {
    try {
      await testFinnhubConfig();
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("test-ai-btn").addEventListener("click", async () => {
    try {
      await testAiConfig();
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("test-exa-btn").addEventListener("click", async () => {
    try {
      await testExaConfig();
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("test-tavily-btn").addEventListener("click", async () => {
    try {
      await testTavilyConfig();
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("refresh-btn").addEventListener("click", async () => {
    try {
      await fetchCompare();
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("financial-refresh-btn").addEventListener("click", async () => {
    try {
      await fetchCompare(true);
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("target-price-btn").addEventListener("click", async () => {
    try {
      await generateTargetPriceAnalysis();
    } catch (err) {
      renderTargetPriceOutput(t("action_failed", { status: err.message }));
    }
  });

  document.getElementById("earnings-btn").addEventListener("click", async () => {
    try {
      await generateFinancialAnalysis();
    } catch (err) {
      renderEarningsOutput(t("action_failed", { status: err.message }));
    }
  });

  document.getElementById("ai-btn").addEventListener("click", async () => {
    try {
      await generateAi();
    } catch (err) {
      renderAiOutput(t("action_failed", { status: err.message }));
    }
  });

  document.getElementById("export-btn").addEventListener("click", async () => {
    try {
      await exportExcel();
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("screenshot-btn").addEventListener("click", async () => {
    try {
      await captureScreen();
    } catch (err) {
      document.getElementById("status").textContent = t("capture_failed", { message: err.message });
    }
  });

  document.getElementById("save-watchlist-btn").addEventListener("click", async () => {
    try {
      await saveWatchlist();
      document.getElementById("status").textContent = t("status_watchlist_saved");
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("load-watchlist-btn").addEventListener("click", async () => {
    try {
      await loadWatchlists();
      document.getElementById("status").textContent = t("status_watchlist_refreshed");
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("copy-target-price-btn").addEventListener("click", async () => {
    try {
      await copyAnalysisOutput("targetPrice");
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("copy-earnings-btn").addEventListener("click", async () => {
    try {
      await copyAnalysisOutput("earnings");
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("copy-ai-btn").addEventListener("click", async () => {
    try {
      await copyAnalysisOutput("ai");
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("earnings-followup-btn").addEventListener("click", async () => {
    try {
      await submitFollowup("earnings");
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("ai-followup-btn").addEventListener("click", async () => {
    try {
      await submitFollowup("ai");
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  ["earnings-followup-input", "ai-followup-input"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const type = id === "earnings-followup-input" ? "earnings" : "ai";
      try {
        await submitFollowup(type);
      } catch (err) {
        document.getElementById("status").textContent = err.message;
      }
    });
  });

  document.getElementById("watchlist-list").addEventListener("click", async e => {
    const loadBtn = e.target.closest(".watchlist-load-btn");
    if (loadBtn) {
      try {
        await loadWatchlistById(loadBtn.dataset.id);
        document.getElementById("status").textContent = t("status_watchlist_loaded");
      } catch (err) {
        document.getElementById("status").textContent = err.message;
      }
      return;
    }

    const renameBtn = e.target.closest(".watchlist-rename-btn");
    if (renameBtn) {
      try {
        const recordId = renameBtn.dataset.id;
        const current = state.watchlist.items.find(item => String(item.id) === String(recordId));
        const currentName = (current?.name || t("watchlist_unknown_name")).trim();
        const nextNameRaw = window.prompt(t("prompt_watchlist_rename"), currentName);
        if (nextNameRaw === null) {
          return;
        }
        const nextName = nextNameRaw.trim();
        if (!nextName) {
          throw new Error(t("err_watchlist_name_empty"));
        }
        const updated = await renameWatchlistById(recordId, nextName);
        document.getElementById("status").textContent = t("status_watchlist_renamed", { name: updated.name });
      } catch (err) {
        document.getElementById("status").textContent = err.message;
      }
      return;
    }

    const deleteBtn = e.target.closest(".watchlist-delete-btn");
    if (deleteBtn) {
      try {
        await deleteWatchlistById(deleteBtn.dataset.id);
        document.getElementById("status").textContent = t("status_watchlist_deleted");
      } catch (err) {
        document.getElementById("status").textContent = err.message;
      }
    }
  });

}

(async function init() {
  loadConfig();
  const defaults = parseSymbols(document.getElementById("symbols").value);
  state.symbols = defaults;
  renderSymbolChips();
  renderStockErrors();
  renderWatchlistMeta();
  renderWatchlistList();
  bindEvents();
  resetFollowup("earnings");
  resetFollowup("ai");

  try {
    await loadWatchlists();
  } catch (err) {
    document.getElementById("status").textContent = err.message;
  }
})();

