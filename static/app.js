const state = {
  symbols: [],
  stocks: [],
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
  finnhubApiKey: "stockcompare.finnhub_api_key",
  aiProvider: "stockcompare.ai_provider",
  aiModel: "stockcompare.ai_model",
  aiApiKey: "stockcompare.ai_api_key",
  aiBaseUrl: "stockcompare.ai_base_url",
  exaApiKey: "stockcompare.exa_api_key",
  tavilyApiKey: "stockcompare.tavily_api_key"
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
    ["change_20d_pct", "20日涨跌幅 (%)"],
    ["change_250d_pct", "250日涨跌幅 (%)"]
  ],
  financial: [
    ["latest_period", "最新财报期"],
    ["revenue_b", "营收 (B USD)"],
    ["revenue_yoy_pct", "营收 YoY (%)"],
    ["net_income_b", "利润 (B USD)"],
    ["net_income_yoy_pct", "利润 YoY (%)"],
    ["eps", "EPS (USD/股)"],
    ["gross_margin_pct", "毛利率 (%)"],
    ["net_margin_pct", "净利率 (%)"]
  ],
  prediction: [
    ["next_quarter_eps_forecast", "预测EPS(Next Quarter)"],
    ["eps_forecast", "预测EPS(Current Year)"],
    ["next_year_eps_forecast", "预测EPS(Next Year)"],
    ["next_earnings_date", "下季度财报日期"]
  ],
  forecast: [
    ["forward_pe", "Forward PE"],
    ["peg", "PEG(5yr expected)"],
    ["ev_to_ebitda", "EV/EBITDA"],
    ["ps", "P/S"],
    ["pb", "P/B"]
  ]
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
    statusLoading: "正在追问财务分析...",
    statusDone: "财务分析追问已更新",
    emptyText: "财务分析生成后可继续追问。"
  },
  ai: {
    inputId: "ai-followup-input",
    buttonId: "ai-followup-btn",
    threadId: "ai-followup-thread",
    endpoint: "/api/ai-analysis-followup",
    statusLoading: "正在追问 AI 建议...",
    statusDone: "AI 建议追问已更新",
    emptyText: "AI 建议生成后可继续追问。"
  }
};

function parseSymbols(raw) {
  return String(raw || "")
    .split(",")
    .map(s => s.trim().toUpperCase())
    .filter(Boolean)
    .filter((s, i, arr) => arr.indexOf(s) === i)
    .slice(0, 10);
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

function renderWatchlistMeta() {
  const el = document.getElementById("watchlist-meta");
  if (!el) return;

  const count = state.watchlist.items.length;
  if (!count) {
    el.textContent = "暂无已保存自选组";
    return;
  }
  const latest = state.watchlist.items[0]?.updated_at;
  el.textContent = `已保存${count}组 (${fmtTime(latest)})`;
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderWatchlistList() {
  const wrap = document.getElementById("watchlist-list");
  if (!wrap) return;
  if (!state.watchlist.items.length) {
    wrap.innerHTML = '<div class="watchlist-empty">暂无已保存自选组</div>';
    return;
  }

  let html = "";
  state.watchlist.items.forEach(item => {
    const symbols = Array.isArray(item.symbols) ? item.symbols.join(", ") : "";
    html += `
      <div class="watchlist-item" data-id="${item.id}">
        <div class="watchlist-title">${escapeHtml(item.name || "未命名")} | ${fmtTime(item.updated_at)}</div>
        <div class="watchlist-actions">
          <button type="button" class="watchlist-load-btn" data-id="${item.id}">加载</button>
          <button type="button" class="watchlist-rename-btn" data-id="${item.id}">重命名</button>
          <button type="button" class="watchlist-delete-btn" data-id="${item.id}">删除</button>
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
    throw new Error(data.error || `加载自选组失败: ${resp.status}`);
  }
  state.watchlist.items = Array.isArray(data.items) ? data.items : [];
  state.watchlist.refreshedAt = new Date().toISOString();
  renderWatchlistMeta();
  renderWatchlistList();
}

async function saveWatchlist() {
  if (!state.symbols.length) {
    throw new Error("请先添加至少1个股票代码后再保存。");
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
    throw new Error(data.error || `保存自选组失败: ${resp.status}`);
  }

  if (nameInput) nameInput.value = "";
  await loadWatchlists();
}

async function loadWatchlistById(recordId) {
  const resp = await fetch(`/api/watchlist/${encodeURIComponent(recordId)}`);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || `加载自选组失败: ${resp.status}`);
  }
  const symbols = Array.isArray(data.symbols) ? parseSymbols(data.symbols.join(",")) : [];
  if (!symbols.length) {
    throw new Error("该自选组为空，无法加载。");
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
    throw new Error(data.error || `删除自选组失败: ${resp.status}`);
  }
  if (!data.ok) {
    throw new Error("删除失败：自选组不存在。");
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
    throw new Error(data.error || `修改自选组名称失败: ${resp.status}`);
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

function renderMarkdownOutput(elementId, markdownText, emptyText = "无返回内容") {
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
    wrap.innerHTML = `<div class="followup-empty">${cfg.emptyText}</div>`;
    return;
  }

  let html = "";
  messages.forEach(msg => {
    const role = msg.role === "assistant" ? "assistant" : "user";
    const roleLabel = role === "assistant" ? "AI" : "你";
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
    return normalized.startsWith("参考来源");
  });
  if (headerIndex < 0) return raw.trim();
  return lines.slice(0, headerIndex).join("\n").trim();
}

function renderAiOutput(markdownText) {
  const cleaned = stripReferenceSection(markdownText);
  state.analysis.ai = cleaned;
  renderMarkdownOutput("ai-output", cleaned, "无返回内容");
}

function renderTargetPriceOutput(markdownText, emptyText = "暂无可用目标价分析。") {
  const cleaned = stripReferenceSection(markdownText);
  state.analysis.targetPrice = cleaned;
  renderMarkdownOutput("target-price-output", cleaned, emptyText);
}

function renderEarningsOutput(markdownText, emptyText = "暂无可用财务分析。") {
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
    throw new Error("复制失败，请手动复制");
  }
}

async function copyAnalysisOutput(type) {
  const mapping = {
    targetPrice: { label: "目标价分析", text: state.analysis.targetPrice },
    earnings: { label: "财务分析", text: state.analysis.earnings },
    ai: { label: "AI投资建议", text: state.analysis.ai }
  };
  const target = mapping[type];
  if (!target) return;

  const text = String(target.text || "").trim();
  if (!text) {
    throw new Error(`暂无可复制的${target.label}内容`);
  }
  await writeClipboardText(text);
  document.getElementById("status").textContent = `${target.label}已复制到剪贴板`;
}

function fmt(value, key) {
  if (value === null || value === undefined) return "--";
  if (key === "latest_period_type") {
    if (String(value).toLowerCase() === "quarterly") return "季度";
    if (String(value).toLowerCase() === "annual") return "年度";
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
    return "请先抓取数据。";
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
        `财报 beat/miss、历史 EPS surprise`,
        `- 最新财报: ${beatMiss.latest_quarter || "--"} | EPS实际=${fmtNumberMaybe(beatMiss.latest_eps_actual)} | EPS预期=${fmtNumberMaybe(beatMiss.latest_eps_estimate)} | Surprise=${fmtPercentMaybe(beatMiss.latest_surprise_pct)} | 结果=${beatMiss.latest_result || "--"}`,
        `- 近4季 surprise: ${surprises || "--"}；Beat=${beatMiss.beat_count_4q ?? "--"}，Miss=${beatMiss.miss_count_4q ?? "--"}，连续Beat=${beatMiss.beat_streak_4q ?? "--"}`,
        `- 结论: ${conclusion.beat_miss || beatMiss.conclusion || "信息不足"}`
      ].join("\n")
    );
  });

  return sections.join("\n\n");
}

function buildEpsTrendMarkdown(stocks) {
  if (!Array.isArray(stocks) || stocks.length === 0) {
    return "请先抓取数据。";
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
        `一致预期变化 EPS Trend（7/30/60/90天）`,
        `- 口径: ${epsTrend.period || "--"} | current=${fmtNumberMaybe(epsTrend.current)} | 7d=${fmtNumberMaybe(epsTrend.d7)} | 30d=${fmtNumberMaybe(epsTrend.d30)} | 60d=${fmtNumberMaybe(epsTrend.d60)} | 90d=${fmtNumberMaybe(epsTrend.d90)}`,
        `- 变化: vs30d=${fmtPercentMaybe(epsTrend.change_vs_30d_pct)}，vs90d=${fmtPercentMaybe(epsTrend.change_vs_90d_pct)} | signal=${epsTrend.signal || "--"}`,
        `- 结论: ${conclusion.eps_trend || epsTrend.conclusion || "信息不足"}`
      ].join("\n")
    );
  });

  return sections.join("\n\n");
}

function renderExpectationPanels(stocks) {
  renderMarkdownOutput("beat-miss-output", buildBeatMissMarkdown(stocks), "暂无可用 beat/miss 数据。");
  renderMarkdownOutput("eps-trend-output", buildEpsTrendMarkdown(stocks), "暂无可用 EPS Trend 数据。");
}

function renderTable(tableId, sectionKey) {
  const table = document.getElementById(tableId);
  const cols = state.stocks.map(s => s.symbol);

  let html = "<thead><tr><th>指标</th>";
  cols.forEach(s => {
    html += `<th>${s}</th>`;
  });
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

async function fetchCompare(forceRefreshFinancial = false) {
  const status = document.getElementById("status");
  if (!state.symbols.length) {
    status.textContent = "请先添加至少1个股票代码。";
    return;
  }

  const cfg = getConfig();

  status.textContent = forceRefreshFinancial ? "正在抓取股票数据（强制刷新财务缓存）..." : "正在抓取股票数据...";
  const symbolsQuery = state.symbols.join(",");
  const headers = {};
  if (cfg.finnhubApiKey) headers["X-Finnhub-Api-Key"] = cfg.finnhubApiKey;
  if (cfg.exaApiKey) headers["X-Exa-Api-Key"] = cfg.exaApiKey;
  if (cfg.tavilyApiKey) headers["X-Tavily-Api-Key"] = cfg.tavilyApiKey;
  if (cfg.aiProvider) headers["X-AI-Provider"] = cfg.aiProvider;
  if (cfg.aiApiKey) headers["X-AI-Api-Key"] = cfg.aiApiKey;
  if (cfg.aiModel) headers["X-AI-Model"] = cfg.aiModel;
  if (cfg.aiBaseUrl) headers["X-AI-Base-Url"] = cfg.aiBaseUrl;
  const resp = await fetch(
    `/api/compare?symbols=${encodeURIComponent(symbolsQuery)}&force_financial_refresh=${forceRefreshFinancial ? "1" : "0"}&_ts=${Date.now()}`,
    {
      cache: "no-store",
      headers
    }
  );

  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || `接口失败: ${resp.status}`);
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
  renderSymbolChips();

  renderTable("realtime-table", "realtime");
  renderTable("financial-table", "financial");
  renderTable("prediction-table", "prediction");
  renderTable("forecast-table", "forecast");
  renderExpectationPanels(state.stocks);
  renderTargetPriceOutput("请点击“生成目标价分析”。");
  renderEarningsOutput("", "请点击“生成财务分析”。");
  renderAiOutput("请点击“生成 AI 综合建议”。");
  resetFollowup("earnings");
  resetFollowup("ai");

  document.getElementById("target-price-btn").disabled = state.stocks.length === 0;
  document.getElementById("earnings-btn").disabled = state.stocks.length === 0;
  document.getElementById("ai-btn").disabled = state.stocks.length === 0;
  status.textContent = `数据更新时间: ${fmtTime(data.generated_at)}`;
}

async function generateTargetPriceAnalysis() {
  const status = document.getElementById("status");
  const cfg = getConfig();

  if (!state.stocks.length) {
    renderTargetPriceOutput("请先抓取数据。");
    return;
  }
  if (!cfg.aiApiKey || !cfg.aiModel) {
    renderTargetPriceOutput("请先填写 AI API Key 和模型。");
    return;
  }

  renderTargetPriceOutput("目标价分析生成中，请稍候...");
  status.textContent = "正在生成目标价分析...";

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
      finnhub_api_key: cfg.finnhubApiKey
    })
  });

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    renderTargetPriceOutput(errData.error || `生成失败: ${resp.status}`);
    return;
  }

  const data = await resp.json();
  renderTargetPriceOutput(data.analysis || "无返回内容");
  status.textContent = data.provider && data.model
    ? `目标价分析已生成（${data.provider} / ${data.model}）`
    : "目标价分析已生成";
}

async function generateFinancialAnalysis() {
  const status = document.getElementById("status");
  const cfg = getConfig();
  const hasAiConfig = Boolean(cfg.aiApiKey && cfg.aiModel);

  if (!state.stocks.length) {
    renderEarningsOutput("请先抓取数据。");
    setFollowupReady("earnings", false);
    return;
  }

  resetFollowup("earnings");
  renderEarningsOutput("财务分析生成中，请稍候...");
  status.textContent = hasAiConfig ? "正在生成财务分析（AI增强）..." : "正在生成财务分析...";

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
      tavily_api_key: cfg.tavilyApiKey
    })
  });

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    renderEarningsOutput(errData.error || `生成失败: ${resp.status}`);
    setFollowupReady("earnings", false);
    return;
  }

  const data = await resp.json();
  renderEarningsOutput(data.analysis || "无返回内容");
  setFollowupReady("earnings", Boolean(String(data.analysis || "").trim()));
  status.textContent = data.provider && data.model
    ? `财务分析已生成（${data.provider} / ${data.model}）`
    : "财务分析已生成";
}

async function generateAi() {
  const status = document.getElementById("status");
  const cfg = getConfig();

  if (!cfg.aiApiKey || !cfg.aiModel) {
    renderAiOutput("请先填写 AI API Key 和模型。");
    setFollowupReady("ai", false);
    return;
  }

  resetFollowup("ai");
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
      exa_api_key: cfg.exaApiKey,
      tavily_api_key: cfg.tavilyApiKey,
      finnhub_api_key: cfg.finnhubApiKey
    })
  });

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    renderAiOutput(errData.error || `调用失败: ${resp.status}`);
    setFollowupReady("ai", false);
    return;
  }

  const data = await resp.json();
  renderAiOutput(data.analysis || "无返回内容");
  setFollowupReady("ai", Boolean(String(data.analysis || "").trim()));
  status.textContent = `AI模型: ${data.provider || "--"} / ${data.model || "--"}`;
}

async function submitFollowup(type) {
  const cfg = followupConfig[type];
  if (!cfg) return;

  const status = document.getElementById("status");
  const input = document.getElementById(cfg.inputId);
  const question = (input?.value || "").trim();
  if (!question) {
    throw new Error("请输入追问内容。");
  }

  const baseAnalysis = String(type === "earnings" ? state.analysis.earnings : state.analysis.ai).trim();
  if (!baseAnalysis) {
    throw new Error("请先生成对应的 AI 分析，再进行追问。");
  }

  const aiCfg = getConfig();
  if (!aiCfg.aiApiKey || !aiCfg.aiModel) {
    throw new Error("请先填写 AI API Key 和模型。");
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
  status.textContent = cfg.statusLoading;

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
        question
      })
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.error || `追问失败: ${resp.status}`);
    }

    const answer = String(data.answer || "无返回内容").trim() || "无返回内容";
    state.followups[type].push({ role: "assistant", content: answer });
    status.textContent = cfg.statusDone;
  } catch (err) {
    state.followups[type].push({ role: "assistant", content: `追问失败：${err.message}` });
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

async function testExaConfig() {
  const status = document.getElementById("status");
  const cfg = getConfig();
  status.textContent = "正在测试 Exa 配置...";

  const resp = await fetch("/api/test-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: "exa",
      exa_api_key: cfg.exaApiKey
    })
  });
  const data = await resp.json().catch(() => ({}));
  status.textContent = data.message || (resp.ok ? "Exa 测试完成" : `Exa 测试失败: ${resp.status}`);
}

async function testTavilyConfig() {
  const status = document.getElementById("status");
  const cfg = getConfig();
  status.textContent = "正在测试 Tavily 配置...";

  const resp = await fetch("/api/test-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: "tavily",
      tavily_api_key: cfg.tavilyApiKey
    })
  });
  const data = await resp.json().catch(() => ({}));
  status.textContent = data.message || (resp.ok ? "Tavily 测试完成" : `Tavily 测试失败: ${resp.status}`);
}

async function captureScreen() {
  const status = document.getElementById("status");
  const target = document.getElementById("capture-target");
  status.textContent = "正在生成截屏...";

  if (typeof window.html2canvas !== "function") {
    throw new Error("截屏库未加载，请刷新页面后重试。");
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
  a.download = `stock_compare_${symbols}_${ts}.png`;
  a.click();
  status.textContent = "截屏已下载。";
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
      renderTargetPriceOutput(`生成失败: ${err.message}`);
    }
  });

  document.getElementById("earnings-btn").addEventListener("click", async () => {
    try {
      await generateFinancialAnalysis();
    } catch (err) {
      renderEarningsOutput(`生成失败: ${err.message}`);
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

  document.getElementById("save-watchlist-btn").addEventListener("click", async () => {
    try {
      await saveWatchlist();
      document.getElementById("status").textContent = "自选组已保存。";
    } catch (err) {
      document.getElementById("status").textContent = err.message;
    }
  });

  document.getElementById("load-watchlist-btn").addEventListener("click", async () => {
    try {
      await loadWatchlists();
      document.getElementById("status").textContent = "自选组列表已刷新。";
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
        document.getElementById("status").textContent = "自选组已加载。";
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
        const currentName = (current?.name || "未命名").trim();
        const nextNameRaw = window.prompt("请输入新的自选组名称", currentName);
        if (nextNameRaw === null) {
          return;
        }
        const nextName = nextNameRaw.trim();
        if (!nextName) {
          throw new Error("自选组名称不能为空");
        }
        const updated = await renameWatchlistById(recordId, nextName);
        document.getElementById("status").textContent = `自选组已改名为 ${updated.name}`;
      } catch (err) {
        document.getElementById("status").textContent = err.message;
      }
      return;
    }

    const deleteBtn = e.target.closest(".watchlist-delete-btn");
    if (deleteBtn) {
      try {
        await deleteWatchlistById(deleteBtn.dataset.id);
        document.getElementById("status").textContent = "自选组已删除。";
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
