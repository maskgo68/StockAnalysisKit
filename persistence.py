import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

_DB_LOCK = Lock()
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_INITIALIZED_DB_PATHS = set()
_ANALYSIS_TYPES = {"ai", "financial"}
_ANALYSIS_PLACEHOLDER_TEXTS = {
    "analysis result",
    "financial analysis",
    "target analysis",
    "target price analysis",
    "financial result",
    "ai followup",
    "followup answer",
}


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _resolve_db_path(db_path=None):
    if db_path:
        return Path(db_path)
    env_path = str(os.getenv("STOCKANALYSISKIT_DB_PATH", "")).strip()
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parent / "data" / "stockanalysiskit.db"


def _connect(db_path=None):
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_symbols(symbols):
    out = []
    for raw in symbols or []:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in out:
            continue
        if not _SYMBOL_PATTERN.match(symbol):
            continue
        out.append(symbol)
        if len(out) >= 10:
            break
    return out


def _normalize_analysis_type(value):
    raw = str(value or "").strip().lower()
    return raw if raw in _ANALYSIS_TYPES else "ai"


def _normalize_symbol(value):
    symbol = str(value or "").strip().upper()
    if not symbol or not _SYMBOL_PATTERN.match(symbol):
        return None
    return symbol


def _is_placeholder_analysis_text(value):
    text = str(value or "").strip().lower()
    return text in _ANALYSIS_PLACEHOLDER_TEXTS


def init_storage(db_path=None):
    target_path = _resolve_db_path(db_path)
    cache_key = str(target_path.resolve())
    if cache_key in _INITIALIZED_DB_PATHS and target_path.exists():
        return

    with _DB_LOCK:
        if cache_key in _INITIALIZED_DB_PATHS and target_path.exists():
            return

        conn = _connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    symbols_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS watchlist_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_watchlist_items_updated_at
                ON watchlist_items (updated_at DESC);

                CREATE TABLE IF NOT EXISTS financial_cache (
                    symbol TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    analysis_type TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    language TEXT,
                    analysis TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_analysis_history_symbol_created_at
                ON analysis_history (symbol, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_analysis_history_created_at
                ON analysis_history (created_at DESC);

                CREATE TABLE IF NOT EXISTS investment_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_investment_notes_symbol_created_at
                ON investment_notes (symbol, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_investment_notes_created_at
                ON investment_notes (created_at DESC);
                """
            )

            # 兼容旧版本单条 watchlist：首次升级时迁移到 watchlist_items。
            item_count = conn.execute("SELECT COUNT(*) FROM watchlist_items").fetchone()[0]
            if int(item_count or 0) == 0:
                row = conn.execute("SELECT symbols_json, updated_at FROM watchlist WHERE id = 1").fetchone()
                if row:
                    try:
                        symbols = _normalize_symbols(json.loads(row["symbols_json"]))
                    except Exception:
                        symbols = []
                    if symbols:
                        migrated_at = str(row["updated_at"] or _utc_now_iso())
                        conn.execute(
                            """
                            INSERT INTO watchlist_items(name, symbols_json, created_at, updated_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                "默认自选",
                                json.dumps(symbols, ensure_ascii=False),
                                migrated_at,
                                migrated_at,
                            ),
                        )
                    # 迁移来源只消费一次，避免用户删除后被反复“回迁”。
                    conn.execute("DELETE FROM watchlist WHERE id = 1")

            # 清理已下线的 AI 历史记录持久化结构与数据。
            conn.executescript(
                """
                DROP INDEX IF EXISTS idx_ai_history_created_at;
                DROP TABLE IF EXISTS ai_history;
                """
            )
            conn.commit()
            _INITIALIZED_DB_PATHS.add(cache_key)
        finally:
            conn.close()


def _normalize_watchlist_name(name):
    text = str(name or "").strip()
    if not text:
        return None
    if len(text) > 40:
        return text[:40].rstrip()
    return text


def _decode_symbols_json(raw):
    try:
        return _normalize_symbols(json.loads(raw))
    except Exception:
        return []


def _watchlist_row_to_dict(row):
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "name": str(row["name"] or "").strip() or "未命名",
        "symbols": _decode_symbols_json(row["symbols_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_watchlist_entries(limit=100, db_path=None):
    init_storage(db_path=db_path)
    size = max(1, min(int(limit or 100), 500))
    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT id, name, symbols_json, created_at, updated_at
                FROM watchlist_items
                ORDER BY id DESC
                LIMIT ?
                """,
                (size,),
            ).fetchall()
        finally:
            conn.close()
    return [_watchlist_row_to_dict(row) for row in rows]


def create_watchlist_entry(name, symbols, db_path=None):
    init_storage(db_path=db_path)
    normalized_symbols = _normalize_symbols(symbols)
    if not normalized_symbols:
        return None

    normalized_name = _normalize_watchlist_name(name)
    if not normalized_name:
        normalized_name = f"自选{_utc_now_iso()[5:16].replace('-', '').replace(':', '')}"

    ts = _utc_now_iso()
    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO watchlist_items(name, symbols_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    normalized_name,
                    json.dumps(normalized_symbols, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )
            new_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()
    return new_id


def get_watchlist_entry(watchlist_id, db_path=None):
    init_storage(db_path=db_path)
    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                """
                SELECT id, name, symbols_json, created_at, updated_at
                FROM watchlist_items
                WHERE id = ?
                """,
                (int(watchlist_id),),
            ).fetchone()
        finally:
            conn.close()
    return _watchlist_row_to_dict(row)


def update_watchlist_entry_name(watchlist_id, name, db_path=None):
    init_storage(db_path=db_path)
    normalized_name = _normalize_watchlist_name(name)
    if not normalized_name:
        return None

    ts = _utc_now_iso()
    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            cur = conn.execute(
                """
                UPDATE watchlist_items
                SET name = ?, updated_at = ?
                WHERE id = ?
                """,
                (normalized_name, ts, int(watchlist_id)),
            )
            conn.commit()
            if cur.rowcount <= 0:
                return None
        finally:
            conn.close()
    return get_watchlist_entry(watchlist_id, db_path=db_path)


def delete_watchlist_entry(watchlist_id, db_path=None):
    init_storage(db_path=db_path)
    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            cur = conn.execute("DELETE FROM watchlist_items WHERE id = ?", (int(watchlist_id),))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def get_cached_financial_bundle(symbol, ttl_hours=12, db_path=None):
    init_storage(db_path=db_path)
    if ttl_hours is not None and float(ttl_hours) <= 0:
        return None

    target = str(symbol or "").strip().upper()
    if not target:
        return None

    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT payload_json, updated_at FROM financial_cache WHERE symbol = ?",
                (target,),
            ).fetchone()
        finally:
            conn.close()

    if not row:
        return None

    if ttl_hours is not None:
        try:
            updated_at = datetime.fromisoformat(str(row["updated_at"]))
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - updated_at > timedelta(hours=float(ttl_hours)):
                return None
        except Exception:
            return None

    try:
        payload = json.loads(row["payload_json"])
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def set_cached_financial_bundle(symbol, financial, ai_financial_context, db_path=None):
    init_storage(db_path=db_path)
    target = str(symbol or "").strip().upper()
    if not target:
        return

    payload = {
        "financial": financial if isinstance(financial, dict) else {},
        "ai_financial_context": ai_financial_context if isinstance(ai_financial_context, dict) else {},
    }
    updated_at = _utc_now_iso()

    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO financial_cache(symbol, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (target, json.dumps(payload, ensure_ascii=False), updated_at),
            )
            conn.commit()
        finally:
            conn.close()


def _analysis_history_row_to_dict(row):
    if not row:
        return None
    try:
        symbols = _normalize_symbols(json.loads(str(row["symbols_json"] or "[]")))
    except Exception:
        symbols = []
    return {
        "id": int(row["id"]),
        "symbol": str(row["symbol"] or "").strip().upper(),
        "symbols": symbols,
        "analysis_type": _normalize_analysis_type(row["analysis_type"]),
        "provider": str(row["provider"] or "").strip() or None,
        "model": str(row["model"] or "").strip() or None,
        "language": str(row["language"] or "").strip() or None,
        "analysis": str(row["analysis"] or "").strip(),
        "created_at": row["created_at"],
    }


def create_analysis_history_entry(
    symbols,
    analysis_type,
    analysis,
    provider=None,
    model=None,
    language=None,
    db_path=None,
):
    init_storage(db_path=db_path)

    normalized_symbols = _normalize_symbols(symbols)
    text = str(analysis or "").strip()
    if not normalized_symbols or not text or _is_placeholder_analysis_text(text):
        return 0

    normalized_type = _normalize_analysis_type(analysis_type)
    normalized_provider = str(provider or "").strip() or None
    normalized_model = str(model or "").strip() or None
    normalized_language = str(language or "").strip().lower() or None
    if normalized_language and normalized_language not in {"zh", "en"}:
        normalized_language = normalized_language[:2]
    if normalized_language and normalized_language not in {"zh", "en"}:
        normalized_language = None

    ts = _utc_now_iso()
    symbols_json = json.dumps(normalized_symbols, ensure_ascii=False)

    inserted_count = 0
    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            for symbol in normalized_symbols:
                latest = conn.execute(
                    """
                    SELECT created_at
                    FROM analysis_history
                    WHERE symbol = ?
                      AND analysis_type = ?
                      AND analysis = ?
                      AND COALESCE(provider, '') = ?
                      AND COALESCE(model, '') = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (
                        symbol,
                        normalized_type,
                        text,
                        str(normalized_provider or ""),
                        str(normalized_model or ""),
                    ),
                ).fetchone()
                if latest:
                    try:
                        latest_at = datetime.fromisoformat(str(latest["created_at"]))
                        if latest_at.tzinfo is None:
                            latest_at = latest_at.replace(tzinfo=timezone.utc)
                        now_at = datetime.fromisoformat(ts)
                        if now_at - latest_at <= timedelta(minutes=5):
                            continue
                    except Exception:
                        pass

                conn.execute(
                    """
                    INSERT INTO analysis_history(
                        symbol, symbols_json, analysis_type, provider, model, language, analysis, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        symbols_json,
                        normalized_type,
                        normalized_provider,
                        normalized_model,
                        normalized_language,
                        text,
                        ts,
                    ),
                )
                inserted_count += 1
            conn.commit()
        finally:
            conn.close()
    return inserted_count


def list_analysis_history_entries(symbol, analysis_type=None, limit=100, db_path=None):
    init_storage(db_path=db_path)

    target_symbol = str(symbol or "").strip().upper()
    if not _SYMBOL_PATTERN.match(target_symbol):
        return []

    size = max(1, min(int(limit or 100), 500))
    has_type_filter = str(analysis_type or "").strip().lower() in _ANALYSIS_TYPES
    normalized_type = _normalize_analysis_type(analysis_type)

    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            if has_type_filter:
                rows = conn.execute(
                    """
                    SELECT id, symbol, symbols_json, analysis_type, provider, model, language, analysis, created_at
                    FROM analysis_history
                    WHERE symbol = ? AND analysis_type = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (target_symbol, normalized_type, size),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, symbol, symbols_json, analysis_type, provider, model, language, analysis, created_at
                    FROM analysis_history
                    WHERE symbol = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (target_symbol, size),
                ).fetchall()
        finally:
            conn.close()
    return [_analysis_history_row_to_dict(row) for row in rows]


def list_analysis_history_symbols(limit=200, db_path=None):
    init_storage(db_path=db_path)
    size = max(1, min(int(limit or 200), 500))

    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT symbol, COUNT(*) AS history_count, MAX(created_at) AS latest_created_at
                FROM analysis_history
                GROUP BY symbol
                ORDER BY latest_created_at DESC, symbol ASC
                LIMIT ?
                """,
                (size,),
            ).fetchall()
        finally:
            conn.close()

    return [
        {
            "symbol": str(row["symbol"] or "").strip().upper(),
            "history_count": int(row["history_count"] or 0),
            "latest_created_at": row["latest_created_at"],
        }
        for row in rows
    ]


def _investment_note_row_to_dict(row):
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "symbol": str(row["symbol"] or "").strip().upper(),
        "content": str(row["content"] or "").strip(),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_investment_note(symbol, content, db_path=None):
    init_storage(db_path=db_path)

    target_symbol = _normalize_symbol(symbol)
    text = str(content or "").strip()
    if not target_symbol or not text:
        return 0

    ts = _utc_now_iso()
    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO investment_notes(symbol, content, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (target_symbol, text, ts, ts),
            )
            new_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()
    return new_id


def list_investment_notes(symbol, limit=200, db_path=None):
    init_storage(db_path=db_path)

    target_symbol = _normalize_symbol(symbol)
    if not target_symbol:
        return []

    size = max(1, min(int(limit or 200), 500))
    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT id, symbol, content, created_at, updated_at
                FROM investment_notes
                WHERE symbol = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (target_symbol, size),
            ).fetchall()
        finally:
            conn.close()

    return [_investment_note_row_to_dict(row) for row in rows]


def delete_investment_note(note_id, db_path=None):
    init_storage(db_path=db_path)
    try:
        target_id = int(note_id)
    except Exception:
        return False
    if target_id <= 0:
        return False

    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            cur = conn.execute("DELETE FROM investment_notes WHERE id = ?", (target_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def list_investment_note_symbols(limit=200, db_path=None):
    init_storage(db_path=db_path)
    size = max(1, min(int(limit or 200), 500))

    with _DB_LOCK:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT symbol, COUNT(*) AS note_count, MAX(created_at) AS latest_created_at
                FROM investment_notes
                GROUP BY symbol
                ORDER BY latest_created_at DESC, symbol ASC
                LIMIT ?
                """,
                (size,),
            ).fetchall()
        finally:
            conn.close()

    return [
        {
            "symbol": str(row["symbol"] or "").strip().upper(),
            "note_count": int(row["note_count"] or 0),
            "latest_created_at": row["latest_created_at"],
        }
        for row in rows
    ]
