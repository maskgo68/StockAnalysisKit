import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

_DB_LOCK = Lock()
_SYMBOL_PATTERN = re.compile(r"^[A-Z.\-]{1,10}$")
_INITIALIZED_DB_PATHS = set()


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


def get_watchlist_symbols(db_path=None):
    # 兼容旧调用：返回最近一条自选组的 symbols。
    items = list_watchlist_entries(limit=1, db_path=db_path)
    if not items:
        return {"symbols": [], "updated_at": None}
    return {"symbols": items[0]["symbols"], "updated_at": items[0]["updated_at"]}


def save_watchlist_symbols(symbols, db_path=None):
    # 兼容旧调用：作为新一条自选组保存。
    new_id = create_watchlist_entry(name=None, symbols=symbols, db_path=db_path)
    item = get_watchlist_entry(new_id, db_path=db_path) if new_id else None
    if not item:
        return {"symbols": [], "updated_at": None}
    return {"symbols": item["symbols"], "updated_at": item["updated_at"]}


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
