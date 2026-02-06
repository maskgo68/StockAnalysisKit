const state = {
  symbols: [],
  stocks: []
};

const storageKeys = {
  finnhubApiKey: "stockcompare.finnhub_api_key",
  aiProvider: "stockcompare.ai_provider",
  aiModel: "stockcompare.ai_model",
  aiApiKey: "stockcompare.ai_api_key",
  aiBaseUrl: "stockcompare.ai_base_url"
};

const defaultModels = {
  openai: "gpt-4.1-mini",
  gemini: "gemini-2.0-flash",
  claude: "claude-3-5-sonnet-latest"
};

const metrics = {
  realtime: [
    ["price", "股价 (USD)"],
    ["change_pct", "涨跌幅 (%)"],
    ["market_cap_b", "总市值 (B USD)"],
    ["turnover_b", "成交额 (B USD)"],
    ["pe_ttm", "PE TTM"],
    ["change_5d_pct", "5日涨跌幅 (%)"],
    ["change_20d_pct", "20日涨跌幅 (%)"]
  ],
  financial: [
    ["revenue_b", "营收 (B USD)"],
    ["revenue_yoy_pct", "营收 YoY (%)"],
    ["net_income_b", "利润 (B USD)"],
    ["net_income_yoy_pct", "利润 YoY (%)"],
    ["eps", "EPS (USD/股)"],
    ["gross_margin_pct", "毛利率 (%)"],
    ["net_margin_pct", "净利率 (%)"]
  ],
  forecast: [
    ["forward_pe", "Forward PE"],
    ["peg", "PEG"],
    ["eps_forecast", "预测 EPS (USD/股)"],
    ["eps_forecast_yoy_pct", "预测 EPS YoY (%)"]
  ]
};

const percentKeys = new Set([
  "change_pct",
  "change_5d_pct",
  "change_20d_pct",
  "revenue_yoy_pct",
  "net_income_yoy_pct",
  "gross_margin_pct",
  "net_margin_pct",
  "eps_forecast_yoy_pct"
]);

function parseSymbols(raw) {
  return raw
    .split(",")
    .map(s => s.trim().toUpperCase())
    .filter(Boolean)
    .filter((s, i, arr) => arr.indexOf(s) === i)
    .slice(0, 10);
}

function syncHiddenSymbols() {
  document.getElementById("symbols").value = state.symbols.join(",");
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
    aiBaseUrl: document.getElementById("ai-base-url").value.trim()
  };
}

function saveConfig() {
  const cfg = getConfig();
  localStorage.setItem(storageKeys.finnhubApiKey, cfg.finnhubApiKey);
  localStorage.setItem(storageKeys.aiProvider, cfg.aiProvider);
  localStorage.setItem(storageKeys.aiModel, cfg.aiModel);
  localStorage.setItem(storageKeys.aiApiKey, cfg.aiApiKey);
  localStorage.setItem(storageKeys.aiBaseUrl, cfg.aiBaseUrl);
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

  applyProviderDefaults(false);
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
    baseUrlInput.placeholder = "默认 https://api.openai.com/v1";
  } else {
    baseUrlInput.disabled = true;
    baseUrlInput.placeholder = "仅 OpenAI 兼容 Provider 需要";
  }
}

function renderSymbolChips() {
  const wrap = document.getElementById("symbol-chips");
  if (!state.symbols.length) {
    wrap.innerHTML = '<span class="chip-empty">请先添加股票代码</span>';
    syncHiddenSymbols();
    return;
  }

  let html = "";
  state.symbols.forEach(symbol => {
    html += `<span class="chip">${symbol}<button type="button" class="chip-del" data-symbol="${symbol}" title="删除">×</button></span>`;
  });
  wrap.innerHTML = html;
  syncHiddenSymbols();
}

function addSymbol(symbolRaw) {
  const symbol = (symbolRaw || "").trim().toUpperCase();
  if (!symbol) return;
  if (!/^[A-Z.\-]{1,10}$/.test(symbol)) return;
  if (state.symbols.includes(symbol)) return;
  if (state.symbols.length >= 10) return;
  state.symbols.push(symbol);
  renderSymbolChips();
}

function removeSymbol(symbol) {
  state.symbols = state.symbols.filter(s => s !== symbol);
  renderSymbolChips();
}

function fmt(value, key) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  if (percentKeys.has(key)) return `${Number(value).toFixed(2)}%`;
  return Number(value).toFixed(2);
}

function renderAiOutput(markdownText) {
  const output = document.getElementById("ai-output");
  const text = String(markdownText || "").trim();
  if (!text) {
    output.textContent = "无返回内容";
    return;
  }

  if (window.marked && window.DOMPurify) {
    const html = window.marked.parse(text, { breaks: true, gfm: true });
    output.innerHTML = window.DOMPurify.sanitize(html);
    return;
  }

  output.textContent = text;
}

function renderTable(tableId, sectionKey) {
  const table = document.getElementById(tableId);
  const cols = state.stocks.map(s => s.symbol);

  let html = "<thead><tr><th>指标</th>";
  cols.forEach(s => { html += `<th>${s}</th>`; });
  html += "</tr></thead><tbody>";

  metrics[sectionKey].forEach(([key, label]) => {
    html += `<tr><td>${label}</td>`;
    state.stocks.forEach(stock => {
      const v = stock[sectionKey]?.[key];
      html += `<td>${fmt(v, key)}</td>`;
    });
    html += "</tr>";
  });

  html += "</tbody>";
  table.innerHTML = html;
}

async function fetchCompare() {
  const status = document.getElementById("status");
  if (!state.symbols.length) {
    status.textContent = "请先添加至少1个股票代码";
    return;
  }

  const cfg = getConfig();
  if (!cfg.finnhubApiKey) {
    status.textContent = "请先填写 Finnhub API Key";
    return;
  }

  status.textContent = "正在抓取股票数据...";
  const symbolsQuery = state.symbols.join(",");
  const resp = await fetch(`/api/compare?symbols=${encodeURIComponent(symbolsQuery)}`, {
    headers: { "X-Finnhub-Api-Key": cfg.finnhubApiKey }
  });

  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || `接口失败: ${resp.status}`);
  }

  const data = await resp.json();
  state.symbols = data.symbols || state.symbols;
  state.stocks = data.stocks || [];
  renderSymbolChips();

  renderTable("realtime-table", "realtime");
  renderTable("financial-table", "financial");
  renderTable("forecast-table", "forecast");

  document.getElementById("ai-btn").disabled = state.stocks.length === 0;
  status.textContent = `数据更新时间: ${data.generated_at || "--"}`;
}

async function generateAi() {
  const status = document.getElementById("status");
  const cfg = getConfig();

  if (!cfg.aiApiKey || !cfg.aiModel) {
    renderAiOutput("请先填写 AI API Key 和模型。");
    return;
  }

  renderAiOutput("AI 分析中，请稍候...");
  status.textContent = "正在调用 AI...";

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
      finnhub_api_key: cfg.finnhubApiKey
    })
  });

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    renderAiOutput(errData.error || `调用失败: ${resp.status}`);
    return;
  }

  const data = await resp.json();
  renderAiOutput(data.analysis || "无返回内容");
  status.textContent = `AI模型: ${data.provider || "--"} / ${data.model || "--"}`;
}

async function exportExcel() {
  if (!state.symbols.length) return;
  const cfg = getConfig();
  if (!cfg.finnhubApiKey) {
    document.getElementById("status").textContent = "请先填写 Finnhub API Key";
    return;
  }

  const resp = await fetch("/api/export-excel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols: state.symbols, finnhub_api_key: cfg.finnhubApiKey })
  });

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    throw new Error(errData.error || `导出失败: ${resp.status}`);
  }

  const blob = await resp.blob();
  const cd = resp.headers.get("content-disposition") || "";
  const match = /filename=([^;]+)/i.exec(cd);
  const filename = match ? decodeURIComponent(match[1].replaceAll('"', "")) : "stock_compare.xlsx";

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
  status.textContent = "正在测试 Finnhub 配置...";

  const resp = await fetch("/api/test-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target: "finnhub", finnhub_api_key: cfg.finnhubApiKey })
  });
  const data = await resp.json().catch(() => ({}));
  status.textContent = data.message || (resp.ok ? "Finnhub 测试完成" : `Finnhub 测试失败: ${resp.status}`);
}

async function testAiConfig() {
  const status = document.getElementById("status");
  const cfg = getConfig();
  status.textContent = "正在测试 AI 配置...";

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
  status.textContent = data.message || (resp.ok ? "AI 测试完成" : `AI 测试失败: ${resp.status}`);
}

async function captureScreen() {
  const status = document.getElementById("status");
  const target = document.getElementById("capture-target");
  status.textContent = "正在生成截屏...";

  if (typeof window.html2canvas !== "function") {
    throw new Error("截屏库未加载，请刷新页面后重试");
  }

  const canvas = await window.html2canvas(target, {
    scale: 2,
    backgroundColor: "#f6f8fc",
    useCORS: true,
    logging: false
  });

  const a = document.createElement("a");
  const symbols = state.symbols.length ? state.symbols.join("_") : "stocks";
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  a.href = canvas.toDataURL("image/png");
  a.download = `stock_compare_${symbols}_${ts}.png`;
  a.click();
  status.textContent = "截屏已下载";
}

function bindEvents() {
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

  [
    "finnhub-api-key",
    "ai-model",
    "ai-api-key",
    "ai-base-url"
  ].forEach(id => {
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

  document.getElementById("refresh-btn").addEventListener("click", async () => {
    try {
      await fetchCompare();
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("ai-btn").addEventListener("click", async () => {
    try {
      await generateAi();
    } catch (err) {
      renderAiOutput(`生成失败: ${err.message}`);
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
      document.getElementById("status").textContent = `截屏失败: ${err.message}`;
    }
  });
}

(function init() {
  loadConfig();
  const defaults = parseSymbols(document.getElementById("symbols").value || "NVDA");
  state.symbols = defaults;
  renderSymbolChips();
  bindEvents();
  fetchCompare().catch(err => {
    document.getElementById("status").textContent = err.message;
  });
})();
