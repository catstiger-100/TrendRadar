# coding=utf-8
"""
新闻收藏仓库模块。

负责：
- 收藏表建表与迁移
- 收藏新增/删除
- 查询用户收藏状态
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Iterable, List, Optional, Set

from trendradar.storage.news_repository import _get_conn, _put_conn

logger = logging.getLogger(__name__)

SCHEMA_LOCK_KEY = 551202603
_schema_ready = False
_schema_lock = threading.Lock()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS news_article_favorites (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    thought TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    favorite_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (article_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_news_favorites_user_id
    ON news_article_favorites (user_id, favorite_time DESC);

CREATE INDEX IF NOT EXISTS idx_news_favorites_article_id
    ON news_article_favorites (article_id);
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


def add_favorite(
    article_id: int,
    user_id: int,
    thought: str = "",
    title: str = "",
) -> Dict[str, Any]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news_article_favorites (
                    article_id, user_id, thought, title, favorite_time, created_at
                )
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (article_id, user_id) DO UPDATE SET
                    thought = EXCLUDED.thought,
                    title = EXCLUDED.title,
                    favorite_time = NOW()
                RETURNING id, article_id, user_id, thought, title, favorite_time, created_at
                """,
                (article_id, user_id, thought or "", title or ""),
            )
            row = cur.fetchone()
        conn.commit()
        return _row_to_dict(row)
    except Exception as e:
        conn.rollback()
        logger.error(f"收藏文章失败: {e}")
        raise
    finally:
        _put_conn(conn)


def remove_favorite(article_id: int, user_id: int) -> bool:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM news_article_favorites
                WHERE article_id = %s AND user_id = %s
                """,
                (article_id, user_id),
            )
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    except Exception as e:
        conn.rollback()
        logger.error(f"删除收藏失败: {e}")
        raise
    finally:
        _put_conn(conn)


def get_favorite(article_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, article_id, user_id, thought, title, favorite_time, created_at
                FROM news_article_favorites
                WHERE article_id = %s AND user_id = %s
                """,
                (article_id, user_id),
            )
            row = cur.fetchone()
        return _row_to_dict(row) if row else None
    except Exception as e:
        conn.rollback()
        logger.error(f"查询收藏失败: {e}")
        raise
    finally:
        _put_conn(conn)


def get_favorite_map(user_id: int, article_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
    ensure_schema()
    ids = [int(article_id) for article_id in article_ids if article_id is not None]
    if not ids:
        return {}

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, article_id, user_id, thought, title, favorite_time, created_at
                FROM news_article_favorites
                WHERE user_id = %s
                  AND article_id = ANY(%s::int[])
                """,
                (user_id, ids),
            )
            rows = cur.fetchall()
        return {row[1]: _row_to_dict(row) for row in rows}
    except Exception as e:
        conn.rollback()
        logger.error(f"批量查询收藏失败: {e}")
        raise
    finally:
        _put_conn(conn)


def get_favorite_article_ids(user_id: int) -> Set[int]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT article_id
                FROM news_article_favorites
                WHERE user_id = %s
                """,
                (user_id,),
            )
            rows = cur.fetchall()
        return {row[0] for row in rows}
    except Exception as e:
        conn.rollback()
        logger.error(f"查询收藏文章 ID 失败: {e}")
        raise
    finally:
        _put_conn(conn)


def _row_to_dict(row: Any) -> Dict[str, Any]:
    favorite_time = row[5].isoformat() if row[5] else ""
    created_at = row[6].isoformat() if row[6] else ""
    return {
        "id": row[0],
        "article_id": row[1],
        "user_id": row[2],
        "thought": row[3] or "",
        "title": row[4] or "",
        "favorite_time": favorite_time,
        "created_at": created_at,
    }
