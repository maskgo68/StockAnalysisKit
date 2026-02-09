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
