const state = {
  uiLanguage: "zh",
  selectedSymbol: "",
  analysisType: "all",
  symbols: [],
  items: [],
  noteItems: []
};

const storageKeys = {
  uiLanguage: "stockanalysiskit.ui_language"
};

const i18n = {
  zh: {
    document_title: "投资笔记/历史分析",
    lang_toggle: "EN",
    history_title: "投资笔记/历史分析",
    history_hint: "按股票代码查看每次 AI 分析结果，并对比任意两个时间点的结论变化。",
    history_tag_1: "按股票时间线",
    history_tag_2: "快照对比",
    history_tag_3: "AI 记忆",
    symbol_placeholder: "输入股票代码，如 NVDA",
    search_btn: "查看历史",
    type_all: "全部类型",
    type_ai: "投资建议",
    type_financial: "财报分析",
    list_title: "分析时间线（点击展开）",
    compare_title: "上次看法 vs 现在看法",
    left_label: "较早快照",
    right_label: "较新快照",
    note_title: "投资笔记",
    note_history_title: "历史笔记（点击展开）",
    note_placeholder: "记录你对该股票的判断、仓位计划和风险点...",
    note_save_btn: "保存笔记",
    note_delete_btn: "删除",
    note_delete_confirm: "确认删除这条笔记？",
    note_item_title: "我的观点",
    note_empty: "该股票暂无投资笔记",
    status_loading_symbols: "正在加载历史股票列表...",
    status_loading_history: "正在加载历史分析...",
    status_saving_note: "正在保存投资笔记...",
    status_deleting_note: "正在删除笔记...",
    status_loaded_history: "已加载 {{symbol}}：AI历史 {{count}} 条，笔记 {{note_count}} 条",
    status_note_saved: "笔记已保存",
    status_note_deleted: "笔记已删除",
    empty_symbols: "暂无历史记录",
    empty_history: "该股票暂无历史分析",
    empty_compare: "请选择左侧和右侧快照进行对比",
    err_symbol_required: "请先输入股票代码",
    err_note_need_symbol: "请先选择或输入股票代码",
    err_note_need_content: "请输入笔记内容",
    err_note_invalid_id: "笔记 ID 无效",
    err_api: "请求失败: {{status}}",
    type_label_ai: "投资建议",
    type_label_financial: "财报分析"
  },
  en: {
    document_title: "Investment Notes / Analysis History",
    lang_toggle: "中文",
    history_title: "Investment Notes / Analysis History",
    history_hint: "Browse every AI snapshot by symbol and compare views between two dates.",
    history_tag_1: "Per Symbol Timeline",
    history_tag_2: "Snapshot Compare",
    history_tag_3: "AI Memory",
    symbol_placeholder: "Enter symbol, e.g. NVDA",
    search_btn: "Load History",
    type_all: "All Types",
    type_ai: "Investment Advice",
    type_financial: "Financial Analysis",
    list_title: "Timeline (click to expand)",
    compare_title: "Previous View vs Current View",
    left_label: "Earlier Snapshot",
    right_label: "Later Snapshot",
    note_title: "Investment Notes",
    note_history_title: "Historical Notes (click to expand)",
    note_placeholder: "Write your thesis, position plan, and risk triggers...",
    note_save_btn: "Save Note",
    note_delete_btn: "Delete",
    note_delete_confirm: "Delete this note?",
    note_item_title: "My Note",
    note_empty: "No notes for this symbol",
    status_loading_symbols: "Loading symbols...",
    status_loading_history: "Loading analysis history...",
    status_saving_note: "Saving note...",
    status_deleting_note: "Deleting note...",
    status_loaded_history: "Loaded {{symbol}}: {{count}} AI snapshot(s), {{note_count}} note(s)",
    status_note_saved: "Note saved",
    status_note_deleted: "Note deleted",
    empty_symbols: "No history yet",
    empty_history: "No snapshots for this symbol",
    empty_compare: "Select two snapshots to compare",
    err_symbol_required: "Enter a stock symbol first",
    err_note_need_symbol: "Select or enter a symbol first",
    err_note_need_content: "Enter note content",
    err_note_invalid_id: "Invalid note id",
    err_api: "Request failed: {{status}}",
    type_label_ai: "Investment Advice",
    type_label_financial: "Financial Analysis"
  }
};

function t(key, vars = {}) {
  const table = i18n[state.uiLanguage] || i18n.zh;
  let out = table[key] || i18n.en[key] || key;
  Object.entries(vars).forEach(([k, v]) => {
    out = out.replaceAll(`{{${k}}}`, String(v));
  });
  return out;
}

function setStatus(text) {
  document.getElementById("status").textContent = text || "";
}

function fmtTime(value) {
  if (!value) return "--";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

function normalizeSymbol(value) {
  return String(value || "").trim().toUpperCase();
}

function parseResponseError(data, status) {
  if (data && typeof data.error === "string" && data.error.trim()) {
    return data.error.trim();
  }
  return t("err_api", { status });
}

function mergeLatestIso(left, right) {
  if (!left) return right || null;
  if (!right) return left;
  return left > right ? left : right;
}

async function fetchJson(url) {
  const resp = await fetch(url, { method: "GET" });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(parseResponseError(data, resp.status));
  }
  return data;
}

function itemTypeLabel(item) {
  const kind = String((item && item.analysis_type) || "").toLowerCase();
  if (kind === "financial") return t("type_label_financial");
  return t("type_label_ai");
}

function buildItemTitle(item) {
  const when = fmtTime(item.created_at);
  const provider = item.provider ? ` | ${item.provider}` : "";
  const model = item.model ? ` / ${item.model}` : "";
  return `${when} | ${itemTypeLabel(item)}${provider}${model}`;
}

function previewText(item) {
  const text = String((item && item.analysis) || "").replace(/\s+/g, " ").trim();
  if (!text) return "--";
  if (text.length <= 180) return text;
  return `${text.slice(0, 180)}...`;
}

function renderMarkdown(targetId, markdownText, emptyText) {
  const target = document.getElementById(targetId);
  renderMarkdownToElement(target, markdownText, emptyText);
}

function renderMarkdownToElement(target, markdownText, emptyText = "") {
  if (!target) return;
  const text = String(markdownText || "").trim();
  if (!text) {
    target.textContent = emptyText;
    return;
  }

  const html = typeof window.marked?.parse === "function"
    ? window.marked.parse(text)
    : text.replaceAll("\n", "<br>");

  if (window.DOMPurify && typeof window.DOMPurify.sanitize === "function") {
    target.innerHTML = window.DOMPurify.sanitize(html);
  } else {
    target.innerHTML = html;
  }
}

function renderSymbolList() {
  const box = document.getElementById("history-symbols-list");
  box.innerHTML = "";

  if (!state.symbols.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = t("empty_symbols");
    box.appendChild(empty);
    return;
  }

  state.symbols.forEach((item) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-symbol-btn";
    if (item.symbol === state.selectedSymbol) {
      btn.classList.add("active");
    }

    const total = Number(item.total_count || 0);
    btn.textContent = `${item.symbol} (${total})`;
    btn.dataset.symbol = item.symbol;
    btn.addEventListener("click", () => {
      document.getElementById("history-symbol-input").value = item.symbol;
      loadHistory(item.symbol).catch((err) => {
        setStatus(err.message);
      });
    });
    box.appendChild(btn);
  });
}

function renderHistoryList() {
  const box = document.getElementById("history-list");
  box.innerHTML = "";

  if (!state.items.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = t("empty_history");
    box.appendChild(empty);
    return;
  }

  state.items.forEach((item) => {
    const row = document.createElement("article");
    row.className = "history-item";

    const title = document.createElement("div");
    title.className = "history-title";
    title.textContent = buildItemTitle(item);

    const preview = document.createElement("div");
    preview.className = "history-preview";
    preview.textContent = previewText(item);

    row.appendChild(title);
    row.appendChild(preview);
    box.appendChild(row);
  });
}

function renderNoteList() {
  const box = document.getElementById("investment-note-list");
  box.innerHTML = "";

  if (!state.noteItems.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = t("note_empty");
    box.appendChild(empty);
    return;
  }

  state.noteItems.forEach((item) => {
    const row = document.createElement("article");
    row.className = "history-item";

    const title = document.createElement("div");
    title.className = "history-title";
    title.textContent = `${fmtTime(item.created_at)} | ${t("note_item_title")}`;

    const actions = document.createElement("div");
    actions.className = "history-actions";

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "history-delete-btn note-delete-btn";
    deleteBtn.textContent = t("note_delete_btn");
    deleteBtn.addEventListener("click", async () => {
      if (!window.confirm(t("note_delete_confirm"))) return;
      deleteBtn.disabled = true;
      try {
        await deleteInvestmentNote(item.id);
      } catch (err) {
        setStatus(err.message);
      } finally {
        deleteBtn.disabled = false;
      }
    });

    actions.appendChild(deleteBtn);

    const content = document.createElement("div");
    content.className = "note-content";
    renderMarkdownToElement(content, String(item.content || "").trim());

    row.appendChild(title);
    row.appendChild(actions);
    row.appendChild(content);
    box.appendChild(row);
  });
}

function renderCompareSelectors() {
  const left = document.getElementById("history-left-select");
  const right = document.getElementById("history-right-select");

  left.innerHTML = "";
  right.innerHTML = "";

  state.items.forEach((item, idx) => {
    const optionText = buildItemTitle(item);

    const leftOpt = document.createElement("option");
    leftOpt.value = String(idx);
    leftOpt.textContent = optionText;
    left.appendChild(leftOpt);

    const rightOpt = document.createElement("option");
    rightOpt.value = String(idx);
    rightOpt.textContent = optionText;
    right.appendChild(rightOpt);
  });

  if (!state.items.length) {
    document.getElementById("history-left-meta").textContent = "";
    document.getElementById("history-right-meta").textContent = "";
    renderMarkdown("history-left-output", "", t("empty_compare"));
    renderMarkdown("history-right-output", "", t("empty_compare"));
    return;
  }

  right.value = "0";
  left.value = state.items.length > 1 ? "1" : "0";
  renderComparePanels();
}

function renderComparePanels() {
  if (!state.items.length) {
    return;
  }

  const leftIdx = Number(document.getElementById("history-left-select").value || 0);
  const rightIdx = Number(document.getElementById("history-right-select").value || 0);
  const leftItem = state.items[leftIdx] || null;
  const rightItem = state.items[rightIdx] || null;

  document.getElementById("history-left-meta").textContent = leftItem ? buildItemTitle(leftItem) : "";
  document.getElementById("history-right-meta").textContent = rightItem ? buildItemTitle(rightItem) : "";

  renderMarkdown("history-left-output", (leftItem && leftItem.analysis) || "", t("empty_compare"));
  renderMarkdown("history-right-output", (rightItem && rightItem.analysis) || "", t("empty_compare"));
}

async function loadSymbolSummaries() {
  setStatus(t("status_loading_symbols"));

  const [historyData, noteData] = await Promise.all([
    fetchJson("/api/analysis-history/symbols?limit=200"),
    fetchJson("/api/investment-notes/symbols?limit=200")
  ]);

  const summary = new Map();

  const ensureEntry = (rawSymbol) => {
    const symbol = normalizeSymbol(rawSymbol);
    if (!symbol) return null;
    if (!summary.has(symbol)) {
      summary.set(symbol, {
        symbol,
        history_count: 0,
        note_count: 0,
        total_count: 0,
        latest_created_at: null
      });
    }
    return summary.get(symbol);
  };

  (Array.isArray(historyData.items) ? historyData.items : []).forEach((item) => {
    const entry = ensureEntry(item && item.symbol);
    if (!entry) return;
    entry.history_count = Number(item && item.history_count) || 0;
    entry.latest_created_at = mergeLatestIso(entry.latest_created_at, item && item.latest_created_at);
  });

  (Array.isArray(noteData.items) ? noteData.items : []).forEach((item) => {
    const entry = ensureEntry(item && item.symbol);
    if (!entry) return;
    entry.note_count = Number(item && item.note_count) || 0;
    entry.latest_created_at = mergeLatestIso(entry.latest_created_at, item && item.latest_created_at);
  });

  state.symbols = Array.from(summary.values())
    .map((item) => ({
      ...item,
      total_count: Number(item.history_count || 0) + Number(item.note_count || 0)
    }))
    .sort((a, b) => {
      const aKey = String(a.latest_created_at || "");
      const bKey = String(b.latest_created_at || "");
      if (aKey === bKey) return String(a.symbol).localeCompare(String(b.symbol));
      return bKey.localeCompare(aKey);
    });

  renderSymbolList();
  setStatus("");
}

async function loadNotes(symbol) {
  const data = await fetchJson(`/api/investment-notes?symbol=${encodeURIComponent(symbol)}&limit=200`);
  state.noteItems = Array.isArray(data.items) ? data.items : [];
  renderNoteList();
}

async function loadHistory(explicitSymbol) {
  const symbol = normalizeSymbol(explicitSymbol || document.getElementById("history-symbol-input").value);
  if (!symbol) {
    throw new Error(t("err_symbol_required"));
  }

  state.selectedSymbol = symbol;
  state.analysisType = String(document.getElementById("history-type-select").value || "all").toLowerCase();
  document.getElementById("history-symbol-input").value = symbol;

  setStatus(t("status_loading_history"));
  const query = new URLSearchParams({ symbol, limit: "200" });
  if (state.analysisType === "ai" || state.analysisType === "financial") {
    query.set("type", state.analysisType);
  }

  const data = await fetchJson(`/api/analysis-history?${query.toString()}`);
  state.items = Array.isArray(data.items) ? data.items : [];

  await loadNotes(symbol);
  renderSymbolList();
  renderHistoryList();
  renderCompareSelectors();
  setStatus(t("status_loaded_history", { symbol, count: state.items.length, note_count: state.noteItems.length }));
}

async function saveInvestmentNote() {
  const symbol = normalizeSymbol(state.selectedSymbol || document.getElementById("history-symbol-input").value);
  if (!symbol) {
    throw new Error(t("err_note_need_symbol"));
  }

  const input = document.getElementById("investment-note-input");
  const content = String(input.value || "").trim();
  if (!content) {
    throw new Error(t("err_note_need_content"));
  }

  const saveBtn = document.getElementById("investment-note-save-btn");
  saveBtn.disabled = true;
  setStatus(t("status_saving_note"));

  try {
    const resp = await fetch("/api/investment-notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, content })
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(parseResponseError(data, resp.status));
    }

    input.value = "";
    await loadSymbolSummaries();
    await loadHistory(symbol);
    setStatus(t("status_note_saved"));
  } finally {
    saveBtn.disabled = false;
  }
}

async function deleteInvestmentNote(noteId) {
  const id = Number(noteId);
  if (!Number.isInteger(id) || id <= 0) {
    throw new Error(t("err_note_invalid_id"));
  }

  setStatus(t("status_deleting_note"));
  const resp = await fetch(`/api/investment-notes/${encodeURIComponent(String(noteId))}`, {
    method: "DELETE"
  });

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(parseResponseError(data, resp.status));
  }

  const symbol = normalizeSymbol(state.selectedSymbol || document.getElementById("history-symbol-input").value);
  await loadSymbolSummaries();
  if (symbol) {
    await loadHistory(symbol);
  } else {
    state.noteItems = [];
    renderNoteList();
  }
  setStatus(t("status_note_deleted"));
}

function applyLanguage(nextLanguage, persist = true) {
  state.uiLanguage = nextLanguage === "en" ? "en" : "zh";
  if (persist) {
    localStorage.setItem(storageKeys.uiLanguage, state.uiLanguage);
  }

  document.title = t("document_title");
  document.getElementById("language-toggle-btn").textContent = t("lang_toggle");
  document.getElementById("history-title").textContent = t("history_title");
  document.getElementById("history-hint").textContent = t("history_hint");
  document.getElementById("history-tag-1").textContent = t("history_tag_1");
  document.getElementById("history-tag-2").textContent = t("history_tag_2");
  document.getElementById("history-tag-3").textContent = t("history_tag_3");
  document.getElementById("history-symbol-input").placeholder = t("symbol_placeholder");
  document.getElementById("history-search-btn").textContent = t("search_btn");
  document.getElementById("history-list-title").textContent = t("list_title");
  document.getElementById("history-compare-title").textContent = t("compare_title");
  document.getElementById("history-left-label").textContent = t("left_label");
  document.getElementById("history-right-label").textContent = t("right_label");
  document.getElementById("investment-note-title").textContent = t("note_title");
  document.getElementById("investment-note-history-title").textContent = t("note_history_title");
  document.getElementById("investment-note-input").placeholder = t("note_placeholder");
  document.getElementById("investment-note-save-btn").textContent = t("note_save_btn");

  const typeSelect = document.getElementById("history-type-select");
  if (typeSelect.options.length >= 3) {
    typeSelect.options[0].text = t("type_all");
    typeSelect.options[1].text = t("type_ai");
    typeSelect.options[2].text = t("type_financial");
  }

  renderSymbolList();
  renderHistoryList();
  renderNoteList();
  renderCompareSelectors();
}

function bindEvents() {
  document.getElementById("language-toggle-btn").addEventListener("click", () => {
    const next = state.uiLanguage === "en" ? "zh" : "en";
    applyLanguage(next, true);
  });

  document.getElementById("history-search-btn").addEventListener("click", async () => {
    try {
      await loadHistory();
    } catch (err) {
      setStatus(err.message);
    }
  });

  document.getElementById("history-symbol-input").addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    try {
      await loadHistory();
    } catch (err) {
      setStatus(err.message);
    }
  });

  document.getElementById("history-type-select").addEventListener("change", async () => {
    if (!state.selectedSymbol) return;
    try {
      await loadHistory(state.selectedSymbol);
    } catch (err) {
      setStatus(err.message);
    }
  });

  document.getElementById("investment-note-save-btn").addEventListener("click", async () => {
    try {
      await saveInvestmentNote();
    } catch (err) {
      setStatus(err.message);
    }
  });

  document.getElementById("investment-note-input").addEventListener("keydown", async (e) => {
    if (!(e.ctrlKey && e.key === "Enter")) return;
    e.preventDefault();
    try {
      await saveInvestmentNote();
    } catch (err) {
      setStatus(err.message);
    }
  });

  document.getElementById("history-left-select").addEventListener("change", renderComparePanels);
  document.getElementById("history-right-select").addEventListener("change", renderComparePanels);
}

(async function init() {
  const savedLanguage = String(localStorage.getItem(storageKeys.uiLanguage) || "").trim();
  const defaultLanguage = String(document.getElementById("default-ui-language")?.value || "").trim();
  state.uiLanguage = savedLanguage || defaultLanguage || "zh";
  state.uiLanguage = state.uiLanguage.startsWith("en") ? "en" : "zh";

  applyLanguage(state.uiLanguage, false);
  bindEvents();

  try {
    await loadSymbolSummaries();
    if (state.symbols.length > 0) {
      await loadHistory(state.symbols[0].symbol);
    } else {
      renderHistoryList();
      renderNoteList();
      renderCompareSelectors();
    }
  } catch (err) {
    setStatus(err.message);
  }
})();
