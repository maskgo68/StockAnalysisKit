import json
import sqlite3

import persistence


def test_watchlist_entries_crud(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    first_id = persistence.create_watchlist_entry(
        name="核心持仓",
        symbols=["NVDA", "AMD"],
        db_path=str(db_path),
    )
    second_id = persistence.create_watchlist_entry(
        name="观察名单",
        symbols=["AAPL"],
        db_path=str(db_path),
    )
    items = persistence.list_watchlist_entries(db_path=str(db_path))
    detail = persistence.get_watchlist_entry(first_id, db_path=str(db_path))
    deleted = persistence.delete_watchlist_entry(second_id, db_path=str(db_path))
    after = persistence.list_watchlist_entries(db_path=str(db_path))

    assert first_id != second_id
    assert [x["name"] for x in items] == ["观察名单", "核心持仓"]
    assert detail["symbols"] == ["NVDA", "AMD"]
    assert deleted is True
    assert len(after) == 1


def test_update_watchlist_name(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))
    watchlist_id = persistence.create_watchlist_entry(
        name="原名称",
        symbols=["NVDA", "AMD"],
        db_path=str(db_path),
    )

    updated = persistence.update_watchlist_entry_name(
        watchlist_id=watchlist_id,
        name="半导体观察",
        db_path=str(db_path),
    )
    invalid = persistence.update_watchlist_entry_name(
        watchlist_id=watchlist_id,
        name="",
        db_path=str(db_path),
    )

    assert updated is not None
    assert updated["name"] == "半导体观察"
    assert invalid is None


def test_legacy_watchlist_migrates_only_once(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE watchlist (id INTEGER PRIMARY KEY CHECK (id = 1), symbols_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO watchlist(id, symbols_json, updated_at) VALUES (1, ?, ?)",
        (json.dumps(["AMD", "NVDA"]), "2026-02-08T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    persistence.init_storage(db_path=str(db_path))
    items = persistence.list_watchlist_entries(db_path=str(db_path))
    assert len(items) == 1

    assert persistence.delete_watchlist_entry(items[0]["id"], db_path=str(db_path)) is True
    assert persistence.list_watchlist_entries(db_path=str(db_path)) == []


def test_financial_cache_ttl(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    persistence.set_cached_financial_bundle(
        "NVDA",
        financial={"revenue_b": 100.0},
        ai_financial_context={"annual": [], "quarterly": []},
        db_path=str(db_path),
    )
    hit = persistence.get_cached_financial_bundle("NVDA", ttl_hours=12, db_path=str(db_path))
    miss = persistence.get_cached_financial_bundle("NVDA", ttl_hours=0, db_path=str(db_path))

    assert hit is not None
    assert hit["financial"]["revenue_b"] == 100.0
    assert miss is None


def test_ai_history_table_removed_on_init_storage(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE ai_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbols_json TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            analysis TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_ai_history_created_at ON ai_history (created_at DESC)")
    conn.execute(
        "INSERT INTO ai_history(symbols_json, provider, model, analysis, created_at) VALUES (?, ?, ?, ?, ?)",
        ('["NVDA"]', "openai", "gpt-4.1-mini", "old", "2026-02-08T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    persistence.init_storage(db_path=str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        table_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_history'"
        ).fetchone()
        index_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ai_history_created_at'"
        ).fetchone()
    finally:
        conn.close()

    assert table_row is None
    assert index_row is None


def test_init_storage_skips_repeated_initialization_for_same_db(tmp_path, monkeypatch):
    db_path = tmp_path / "stockanalysiskit.db"
    real_connect = persistence._connect
    calls = {"count": 0}

    def wrapped_connect(db_path=None):
        calls["count"] += 1
        return real_connect(db_path=db_path)

    monkeypatch.setattr(persistence, "_connect", wrapped_connect)

    persistence.init_storage(db_path=str(db_path))
    persistence.init_storage(db_path=str(db_path))

    assert calls["count"] == 1


def test_create_and_list_analysis_history_by_symbol(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    persistence.create_analysis_history_entry(
        symbols=["NVDA", "AMD"],
        analysis_type="ai",
        analysis="first snapshot",
        provider="openai",
        model="gpt-4.1-mini",
        language="zh",
        db_path=str(db_path),
    )
    persistence.create_analysis_history_entry(
        symbols=["NVDA"],
        analysis_type="financial",
        analysis="second snapshot",
        provider="openai",
        model="gpt-4.1-mini",
        language="en",
        db_path=str(db_path),
    )

    nvda_items = persistence.list_analysis_history_entries("NVDA", db_path=str(db_path))
    amd_items = persistence.list_analysis_history_entries("AMD", db_path=str(db_path))

    assert len(nvda_items) == 2
    assert nvda_items[0]["analysis"] == "second snapshot"
    assert nvda_items[0]["analysis_type"] == "financial"
    assert nvda_items[0]["symbols"] == ["NVDA"]
    assert nvda_items[1]["analysis"] == "first snapshot"
    assert nvda_items[1]["analysis_type"] == "ai"
    assert nvda_items[1]["symbols"] == ["NVDA", "AMD"]

    assert len(amd_items) == 1
    assert amd_items[0]["analysis"] == "first snapshot"
    assert amd_items[0]["analysis_type"] == "ai"


def test_list_analysis_history_supports_type_filter_and_symbols_summary(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    persistence.create_analysis_history_entry(
        symbols=["NVDA", "AMD"],
        analysis_type="ai",
        analysis="ai snapshot",
        provider="openai",
        model="gpt-4.1-mini",
        language="zh",
        db_path=str(db_path),
    )
    persistence.create_analysis_history_entry(
        symbols=["NVDA"],
        analysis_type="financial",
        analysis="financial snapshot",
        provider="openai",
        model="gpt-4.1-mini",
        language="zh",
        db_path=str(db_path),
    )

    only_ai = persistence.list_analysis_history_entries("NVDA", analysis_type="ai", db_path=str(db_path))
    symbols = persistence.list_analysis_history_symbols(db_path=str(db_path))

    assert len(only_ai) == 1
    assert only_ai[0]["analysis_type"] == "ai"
    assert only_ai[0]["analysis"] == "ai snapshot"

    assert [item["symbol"] for item in symbols] == ["NVDA", "AMD"]
    assert symbols[0]["history_count"] == 2
    assert symbols[1]["history_count"] == 1


def test_create_analysis_history_skips_placeholder_stub_text(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    inserted = persistence.create_analysis_history_entry(
        symbols=["NVDA"],
        analysis_type="ai",
        analysis="analysis result",
        provider="openai",
        model="m",
        language="en",
        db_path=str(db_path),
    )
    items = persistence.list_analysis_history_entries("NVDA", db_path=str(db_path))

    assert inserted == 0
    assert items == []


def test_create_analysis_history_deduplicates_recent_same_snapshot(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    first = persistence.create_analysis_history_entry(
        symbols=["NVDA"],
        analysis_type="ai",
        analysis="Long enough AI analysis output text for NVDA.",
        provider="openai",
        model="gpt-4.1-mini",
        language="en",
        db_path=str(db_path),
    )
    second = persistence.create_analysis_history_entry(
        symbols=["NVDA"],
        analysis_type="ai",
        analysis="Long enough AI analysis output text for NVDA.",
        provider="openai",
        model="gpt-4.1-mini",
        language="en",
        db_path=str(db_path),
    )
    items = persistence.list_analysis_history_entries("NVDA", db_path=str(db_path))

    assert first == 1
    assert second == 0
    assert len(items) == 1


def test_create_and_list_investment_notes_by_symbol(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    first_id = persistence.create_investment_note(
        symbol="nvda",
        content="首仓观察：估值偏高，等待回调。",
        db_path=str(db_path),
    )
    second_id = persistence.create_investment_note(
        symbol="NVDA",
        content="加仓条件：下季毛利率继续提升。",
        db_path=str(db_path),
    )
    persistence.create_investment_note(
        symbol="AMD",
        content="观察竞争格局变化。",
        db_path=str(db_path),
    )

    nvda_notes = persistence.list_investment_notes("NVDA", db_path=str(db_path))
    amd_notes = persistence.list_investment_notes("AMD", db_path=str(db_path))

    assert isinstance(first_id, int) and first_id > 0
    assert isinstance(second_id, int) and second_id > first_id
    assert len(nvda_notes) == 2
    assert nvda_notes[0]["content"] == "加仓条件：下季毛利率继续提升。"
    assert nvda_notes[1]["content"] == "首仓观察：估值偏高，等待回调。"
    assert all(item["symbol"] == "NVDA" for item in nvda_notes)
    assert len(amd_notes) == 1
    assert amd_notes[0]["content"] == "观察竞争格局变化。"


def test_list_investment_note_symbols_summary(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    persistence.create_investment_note(symbol="NVDA", content="n1", db_path=str(db_path))
    persistence.create_investment_note(symbol="NVDA", content="n2", db_path=str(db_path))
    persistence.create_investment_note(symbol="AMD", content="a1", db_path=str(db_path))

    symbols = persistence.list_investment_note_symbols(db_path=str(db_path))

    by_symbol = {item["symbol"]: item for item in symbols}
    assert set(by_symbol.keys()) == {"NVDA", "AMD"}
    assert by_symbol["NVDA"]["note_count"] == 2
    assert by_symbol["AMD"]["note_count"] == 1


def test_delete_investment_note(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    note_id = persistence.create_investment_note(
        symbol="NVDA",
        content="需要设置止损纪律",
        db_path=str(db_path),
    )
    deleted = persistence.delete_investment_note(note_id, db_path=str(db_path))
    deleted_again = persistence.delete_investment_note(note_id, db_path=str(db_path))
    notes = persistence.list_investment_notes("NVDA", db_path=str(db_path))

    assert deleted is True
    assert deleted_again is False
    assert notes == []


def test_global_numeric_symbols_supported_in_watchlist_notes_and_history(tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    persistence.init_storage(db_path=str(db_path))

    watchlist_id = persistence.create_watchlist_entry(
        name="global symbols",
        symbols=["0700.HK", "600519.SS", "NVDA"],
        db_path=str(db_path),
    )
    watchlist = persistence.get_watchlist_entry(watchlist_id, db_path=str(db_path))

    note_id = persistence.create_investment_note(
        symbol="0700.HK",
        content="关注腾讯业绩节奏。",
        db_path=str(db_path),
    )
    notes = persistence.list_investment_notes("0700.HK", db_path=str(db_path))

    inserted = persistence.create_analysis_history_entry(
        symbols=["600519.SS"],
        analysis_type="ai",
        analysis="茅台财报跟踪",
        provider="openai",
        model="m",
        language="zh",
        db_path=str(db_path),
    )
    history = persistence.list_analysis_history_entries("600519.SS", db_path=str(db_path))

    assert isinstance(watchlist_id, int) and watchlist_id > 0
    assert watchlist["symbols"] == ["0700.HK", "600519.SS", "NVDA"]
    assert isinstance(note_id, int) and note_id > 0
    assert len(notes) == 1
    assert notes[0]["symbol"] == "0700.HK"
    assert inserted == 1
    assert len(history) == 1
    assert history[0]["symbol"] == "600519.SS"
