# coding=utf-8
"""
用户常用关键词仓库模块。

提供用户关键词的 UPSERT 与查询能力。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List

import psycopg2.extras

from trendradar.storage.news_repository import _get_conn, _put_conn

SCHEMA_LOCK_KEY = 551202607
_schema_ready = False
_schema_lock = threading.Lock()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_keywords (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 1,
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, keyword)
);

CREATE INDEX IF NOT EXISTS idx_user_keywords_user_id
    ON user_keywords (user_id, usage_count DESC);
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


def record_usage(user_id: int, keyword: str) -> None:
    keyword = (keyword or "").strip()
    if not keyword or user_id <= 0:
        return
    ensure_schema()
    conn = _get_conn()
    try:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_keywords (user_id, keyword, usage_count, last_used_at)
                VALUES (%s, %s, 1, NOW())
                ON CONFLICT (user_id, keyword) DO UPDATE SET
                    usage_count = user_keywords.usage_count + 1,
                    last_used_at = NOW()
                """,
                (user_id, keyword),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        _put_conn(conn)


def get_user_keywords(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """
    返回该用户使用过的关键词，按使用次数倒序、最近使用时间倒序排列。

    Args:
        user_id: 用户 ID
        limit: 返回条数上限（默认 20；传入非正数视为不限制）
    """
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if limit and limit > 0:
                cur.execute(
                    """
                    SELECT keyword, usage_count
                    FROM user_keywords
                    WHERE user_id = %s
                    ORDER BY usage_count DESC, last_used_at DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT keyword, usage_count
                    FROM user_keywords
                    WHERE user_id = %s
                    ORDER BY usage_count DESC, last_used_at DESC
                    """,
                    (user_id,),
                )
            return [{"keyword": row["keyword"], "usage_count": row["usage_count"]} for row in cur.fetchall()]
    except Exception:
        conn.rollback()
        return []
    finally:
        _put_conn(conn)
