# coding=utf-8
"""
新闻分享仓库模块。

负责：
- 分享表建表与迁移
- 创建/更新分享记录
- 查询分享详情
"""

from __future__ import annotations

import logging
import secrets
import threading
from typing import Any, Dict, Optional

from trendradar.storage.news_repository import _get_conn, _put_conn

logger = logging.getLogger(__name__)

SCHEMA_LOCK_KEY = 551202604
_schema_ready = False
_schema_lock = threading.Lock()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS news_article_shares (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    thought TEXT NOT NULL DEFAULT '',
    share_token TEXT NOT NULL UNIQUE,
    share_url TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (article_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_news_shares_article_id
    ON news_article_shares (article_id);

CREATE INDEX IF NOT EXISTS idx_news_shares_user_id
    ON news_article_shares (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_shares_share_token
    ON news_article_shares (share_token);
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


def upsert_share(
    article_id: int,
    user_id: int,
    title: str,
    thought: str,
    share_base_url: str,
) -> Dict[str, Any]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, article_id, user_id, title, thought, share_token, share_url, created_at, updated_at
                FROM news_article_shares
                WHERE article_id = %s AND user_id = %s
                """,
                (article_id, user_id),
            )
            row = cur.fetchone()

            if row:
                share_token = row[5]
            else:
                share_token = _generate_share_token()

            share_url = _build_share_url(share_base_url, share_token)
            cur.execute(
                """
                INSERT INTO news_article_shares (
                    article_id, user_id, title, thought, share_token, share_url, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (article_id, user_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    thought = EXCLUDED.thought,
                    share_url = EXCLUDED.share_url,
                    updated_at = NOW()
                RETURNING id, article_id, user_id, title, thought, share_token, share_url, created_at, updated_at
                """,
                (article_id, user_id, title or "", thought or "", share_token, share_url),
            )
            saved = cur.fetchone()
        conn.commit()
        return _row_to_dict(saved)
    except Exception as e:
        conn.rollback()
        logger.error(f"保存分享记录失败: {e}")
        raise
    finally:
        _put_conn(conn)


def get_share_by_article_and_user(article_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, article_id, user_id, title, thought, share_token, share_url, created_at, updated_at
                FROM news_article_shares
                WHERE article_id = %s AND user_id = %s
                """,
                (article_id, user_id),
            )
            row = cur.fetchone()
        return _row_to_dict(row) if row else None
    except Exception as e:
        conn.rollback()
        logger.error(f"查询分享记录失败: {e}")
        raise
    finally:
        _put_conn(conn)


def get_share_detail_by_token(share_token: str) -> Optional[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.id,
                    s.article_id,
                    s.user_id,
                    s.title AS shared_title,
                    s.thought,
                    s.share_token,
                    s.share_url,
                    s.created_at,
                    s.updated_at,
                    a.title,
                    a.source_name,
                    a.summary,
                    a.content,
                    a.published_at,
                    u.full_name,
                    u.username
                FROM news_article_shares s
                JOIN news_articles a ON a.id = s.article_id
                JOIN auth_users u ON u.id = s.user_id
                WHERE s.share_token = %s
                """,
                (share_token,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "article_id": row[1],
            "user_id": row[2],
            "shared_title": row[3] or "",
            "thought": row[4] or "",
            "share_token": row[5] or "",
            "share_url": row[6] or "",
            "created_at": row[7].isoformat() if row[7] else "",
            "updated_at": row[8].isoformat() if row[8] else "",
            "title": row[9] or "",
            "source_name": row[10] or "",
            "summary": row[11] or "",
            "content": row[12] or "",
            "published_at": row[13].isoformat() if row[13] else "",
            "share_user_name": row[14] or row[15] or "",
        }
    except Exception as e:
        conn.rollback()
        logger.error(f"按 token 查询分享详情失败: {e}")
        raise
    finally:
        _put_conn(conn)


def _generate_share_token() -> str:
    return secrets.token_urlsafe(10)


def _build_share_url(base_url: str, share_token: str) -> str:
    normalized_base = (base_url or "").rstrip("/")
    return f"{normalized_base}/console/share/{share_token}"


def _row_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": row[0],
        "article_id": row[1],
        "user_id": row[2],
        "title": row[3] or "",
        "thought": row[4] or "",
        "share_token": row[5] or "",
        "share_url": row[6] or "",
        "created_at": row[7].isoformat() if row[7] else "",
        "updated_at": row[8].isoformat() if row[8] else "",
    }
