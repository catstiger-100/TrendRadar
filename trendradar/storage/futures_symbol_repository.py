# coding=utf-8
"""
期货品种仓库模块。

提供期货品种维护所需的 PostgreSQL CRUD 能力。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List

import psycopg2.extras

from trendradar.storage.news_repository import _get_conn, _put_conn

SCHEMA_LOCK_KEY = 551202606
_schema_ready = False
_schema_lock = threading.Lock()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS futures_symbols (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    sector TEXT NOT NULL DEFAULT '',
    exchange TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_futures_symbols_name_unique
    ON futures_symbols (name);

CREATE INDEX IF NOT EXISTS idx_futures_symbols_exchange
    ON futures_symbols (exchange);

CREATE INDEX IF NOT EXISTS idx_futures_symbols_sector
    ON futures_symbols (sector);
"""


def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return

    with _schema_lock:
        if _schema_ready:
            return

        conn = _get_conn()
        try:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK_KEY,))
                cur.execute(SCHEMA_SQL)
            conn.commit()
            _schema_ready = True
        except Exception:
            conn.rollback()
            raise
        finally:
            _put_conn(conn)


def list_symbols() -> List[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, code, sector, exchange, created_at, updated_at
                FROM futures_symbols
                ORDER BY exchange, sector, code, id
                """
            )
            return [_row_to_dict(row) for row in cur.fetchall()]
    finally:
        _put_conn(conn)


def create_symbol(name: str, code: str, sector: str = "", exchange: str = "") -> Dict[str, Any]:
    ensure_schema()
    payload = _validate_payload(name, code, sector, exchange)
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO futures_symbols (name, code, sector, exchange, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                RETURNING id, name, code, sector, exchange, created_at, updated_at
                """,
                (
                    payload["name"],
                    payload["code"],
                    payload["sector"],
                    payload["exchange"],
                ),
            )
            row = cur.fetchone()
        conn.commit()
        return _row_to_dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def update_symbol(symbol_id: int, name: str, code: str, sector: str = "", exchange: str = "") -> Dict[str, Any]:
    ensure_schema()
    if symbol_id <= 0:
        raise ValueError("期货品种 ID 无效")
    payload = _validate_payload(name, code, sector, exchange)
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE futures_symbols
                SET
                    name = %s,
                    code = %s,
                    sector = %s,
                    exchange = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, name, code, sector, exchange, created_at, updated_at
                """,
                (
                    payload["name"],
                    payload["code"],
                    payload["sector"],
                    payload["exchange"],
                    symbol_id,
                ),
            )
            row = cur.fetchone()
        if not row:
            raise ValueError("期货品种不存在")
        conn.commit()
        return _row_to_dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def delete_symbol(symbol_id: int) -> None:
    ensure_schema()
    if symbol_id <= 0:
        raise ValueError("期货品种 ID 无效")
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM futures_symbols WHERE id = %s", (symbol_id,))
            if cur.rowcount <= 0:
                raise ValueError("期货品种不存在")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def _validate_payload(name: str, code: str, sector: str, exchange: str) -> Dict[str, str]:
    normalized_name = (name or "").strip()
    normalized_code = (code or "").strip().upper()
    normalized_sector = (sector or "").strip()
    normalized_exchange = (exchange or "").strip()

    if not normalized_name:
        raise ValueError("品种名称不能为空")
    if not normalized_code:
        raise ValueError("品种代码不能为空")

    return {
        "name": normalized_name,
        "code": normalized_code,
        "sector": normalized_sector,
        "exchange": normalized_exchange,
    }


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"] or "",
        "code": row["code"] or "",
        "sector": row["sector"] or "",
        "exchange": row["exchange"] or "",
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
    }
